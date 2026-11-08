"""Command line interface for the Apple TV Remote bridge."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

from . import __version__
from .cec import CecConfig, cec_adapters, find_policy
from .config import (
    Config,
    config_text,
    default_config_path,
    load_config,
    write_default_config,
)
from .notify import available as notification_available
from .notify import notify
from .output import OutputError, make_output, uinput_status
from .pairing import PairingGate
from .palette import (
    blur_corner_radius,
    blur_corner_setting,
    blur_ignores_region,
    detect_corner_radius,
)
from .pin_display import PinDisplay, choose_mode
from .server import Identity, RemoteServer

SERVICE_TYPE = "_companion-link._tcp.local."
_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers


def local_ip() -> str:
    """IPv4 address of the interface that routes multicast, else the internet.

    A UDP connect does not send a packet; it only asks the kernel to select a
    source address.  The multicast probe is first because that is the interface
    mDNS will use.
    """
    for host in ("224.0.0.251", "8.8.8.8"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((host, 5353 if host.startswith("224.") else 53))
                address = sock.getsockname()[0]
                if address and not address.startswith("127."):
                    return address
        except OSError:
            pass
    return socket.gethostbyname(socket.gethostname())


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if not verbose:
        logging.getLogger("pyatv").setLevel(logging.WARNING)
        logging.getLogger("zeroconf").setLevel(logging.WARNING)


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)


def _remove(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _pin_path(cfg: Config) -> Path:
    assert cfg.config_path is not None
    return cfg.config_path.parent / "last-pin"


def _pairing_path(cfg: Config) -> Path:
    assert cfg.config_path is not None
    return cfg.config_path.parent / "pairing"


def _make_pin_handler(cfg: Config, pin_display: PinDisplay):
    def show_pin(pin: str) -> None:
        _write_private(_pin_path(cfg), pin + "\n")
        print(f"\n  Pairing PIN: {pin}\n  Enter it on your iPhone or iPad.\n", flush=True)
        if cfg.pin_display == "none":
            return
        if cfg.pin_display == "notification":
            if not notify(
                "Apple TV Remote",
                f"Pairing PIN: {pin}",
                timeout_ms=max(1, cfg.pairing_window) * 1000,
            ):
                _LOGGER.warning(
                    "PIN notification unavailable; use the PIN printed above "
                    "or 'atv-remote pin' (install libnotify/notify-send)"
                )
            return
        if not pin_display.show(pin, cfg.pairing_window):
            _LOGGER.warning(
                "PIN card unavailable; enter the PIN printed above "
                "(install PySide6, or set pin_display = \"notification\")"
            )

    return show_pin


def _make_paired_handler(cfg: Config, gate: PairingGate, pin_display: PinDisplay):
    def on_paired() -> None:
        gate.close()
        pin_display.clear()
        _remove(_pin_path(cfg))
        if cfg.pin_display == "notification":
            notify("Apple TV Remote", "Paired successfully.")
        print("Paired successfully. The pairing window is now closed.", flush=True)

    return on_paired


# ---------------------------------------------------------------------------
# run


async def _serve(cfg: Config) -> int:
    output = make_output(cfg.backend, cfg.keymap, cfg.device_name, cfg.cec)
    pin_display = PinDisplay(enabled=cfg.pin_display in ("auto", "qt"))
    gate = PairingGate(_pairing_path(cfg), cfg.pairing_window)
    gate.touch()  # first-run convenience: allow pairing for a few minutes
    identity = Identity(cfg.state)

    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        lambda: RemoteServer(
            identity,
            cfg.name,
            output.press,
            _make_pin_handler(cfg, pin_display),
            on_hold=output.hold,
            on_release=output.release,
            pairing_gate=gate,
            on_paired=_make_paired_handler(cfg, gate, pin_display),
        ),
        "0.0.0.0",
        cfg.port,
    )
    port = server.sockets[0].getsockname()[1]
    ip = cfg.address or local_ip()
    if not ip or ip.startswith("127.") or ip == "0.0.0.0":
        server.close()
        output.close()
        raise OSError(
            "no non-loopback IPv4 address found; set 'address' in the config or pass --address"
        )

    zeroconf = AsyncZeroconf(interfaces=[ip])
    service_name = cfg.name.replace(".", "-")
    info = ServiceInfo(
        SERVICE_TYPE,
        f"{service_name}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties=identity.txt_record(),
    )
    try:
        await zeroconf.async_register_service(info)
    except Exception:
        await zeroconf.async_close()
        server.close()
        output.close()
        raise

    device_path = getattr(output, "device_path", "")
    if device_path:
        print(f"Virtual keyboard: {device_path}", flush=True)
    print(f"'{cfg.name}' is live on {ip}:{port} (backend: {output.name}).", flush=True)
    print(
        "On the iPhone: open the Apple TV Remote app (or Control Center) "
        f"and select '{cfg.name}'.\nCtrl+C to stop.",
        flush=True,
    )
    if gate.allowed():
        print(
            f"Pairing window is open for {cfg.pairing_window}s. "
            "The PIN card appears in the top-right.",
            flush=True,
        )

    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover - non-POSIX
            pass

    try:
        await stop.wait()
    finally:
        _LOGGER.info("Shutting down")
        await zeroconf.async_unregister_service(info)
        await zeroconf.async_close()
        server.close()
        # Do not await server.wait_closed(): it waits for every existing
        # Companion connection to close, and a paired iPhone may keep its
        # session open.  Closing the listener and returning lets the event
        # loop drop the connections, so systemd does not time out and SIGABRT.
        output.close()
        _remove(_pin_path(cfg))
    return 0


def cmd_run(args, cfg: Config) -> int:
    if args.name:
        cfg.name = args.name
    if args.address:
        cfg.address = args.address
    if args.port is not None:
        cfg.port = args.port
    if args.backend:
        cfg.backend = args.backend
    if args.device_name:
        cfg.device_name = args.device_name
    if args.pairing_window is not None:
        cfg.pairing_window = args.pairing_window
    if args.state:
        cfg.state = args.state
    cfg.validate()

    try:
        return asyncio.run(_serve(cfg))
    except OutputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # keep a clear foreground/service error
        print(f"error: {exc}", file=sys.stderr)
        if args.verbose:
            raise
        return 1


# ---------------------------------------------------------------------------
# pair / pin


def cmd_pair(args, cfg: Config) -> int:
    gate = PairingGate(_pairing_path(cfg), cfg.pairing_window)
    gate.touch()
    print(
        f"Pairing window open for {cfg.pairing_window} seconds.\n"
        "On the iPhone: open the Apple TV Remote app and select "
        f"'{cfg.name}'.\nThe PIN appears in the top-right card "
        "(or with 'atv-remote pin').",
        flush=True,
    )
    if cfg.pin_display == "notification":
        notify("Apple TV Remote", "Pairing window open. Add the remote on your iPhone.")
    return 0


def cmd_preview_pin(args, cfg: Config) -> int:
    seconds = max(1, args.seconds)
    if cfg.pin_display == "notification":
        if not notify("Apple TV Remote", f"Pairing PIN: {args.pin}", timeout_ms=seconds * 1000):
            print("PIN notification unavailable; install libnotify/notify-send.")
            return 1
        print(f"Showed PIN notification for {seconds}s.", flush=True)
        return 0
    if cfg.pin_display == "none":
        print("pin_display = \"none\"; the PIN is only in the log and 'atv-remote pin'.")
        return 1
    display = PinDisplay(enabled=True)
    if not display.available():
        print("PIN GUI is not available. Check 'atv-remote doctor' and install python3-pyside6.")
        return 1
    if not display.show(args.pin, seconds):
        print("Could not start the PIN GUI.")
        return 1
    print(f"Showing PIN card for {seconds}s (Ctrl+C to close).", flush=True)
    try:
        time.sleep(seconds)
    except KeyboardInterrupt:
        pass
    finally:
        display.clear()
    return 0


def cmd_pin(args, cfg: Config) -> int:
    gate = PairingGate(_pairing_path(cfg), cfg.pairing_window)
    if not gate.allowed():
        print("The pairing window is closed. Run 'atv-remote pair' first.")
        return 1
    pin = _pin_path(cfg)
    if not pin.exists():
        print("No PIN yet. Start a pairing attempt on the iPhone; the PIN appears here.")
        return 1
    print(pin.read_text(encoding="utf-8").strip())
    return 0


# ---------------------------------------------------------------------------
# doctor


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(cmd, check=False, timeout=5, capture_output=True, text=True)
        return result.returncode, (result.stdout + result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def _port_list_allows(ports: list[str], port: int, proto: str) -> bool:
    for item in ports:
        spec, _, item_proto = item.partition("/")
        if item_proto != proto:
            continue
        try:
            if "-" in spec:
                low, high = (int(value) for value in spec.split("-", 1))
                if low <= port <= high:
                    return True
            elif int(spec) == port:
                return True
        except ValueError:
            continue
    return False


def _os_release() -> str:
    try:
        text = Path("/etc/os-release").read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def _package_manager() -> str:
    for name in ("dnf", "apt", "pacman", "zypper", "apk"):
        if shutil.which(name):
            return name
    return "unknown"


def _firewall_note() -> list[str]:
    notes: list[str] = []
    if shutil.which("firewall-cmd"):
        rc, state = _run(["firewall-cmd", "--state"])
        if rc == 0 and state.strip() == "running":
            _, services_out = _run(["firewall-cmd", "--list-services"])
            _, ports_out = _run(["firewall-cmd", "--list-ports"])
            services = services_out.split()
            ports = ports_out.split()
            if "mdns" in services or _port_list_allows(ports, 5353, "udp"):
                notes.append("firewalld: mDNS (UDP 5353) is allowed")
            else:
                notes.extend(
                    [
                        "firewalld: mDNS (UDP 5353) is NOT allowed, so the iPhone may not discover the bridge.",
                        "  temporary:  sudo firewall-cmd --add-service=mdns",
                        "  permanent:  sudo firewall-cmd --permanent --add-service=mdns && sudo firewall-cmd --reload",
                        "  (the TCP control port is in FedoraWorkstation's 1025-65535 range, so only mDNS needs opening)",
                    ]
                )
    if shutil.which("ufw"):
        notes.append("ufw: allow discovery with  sudo ufw allow 5353/udp")
    return notes


def cmd_unpair(args, cfg: Config) -> int:
    """Remove one/all paired phone keys from the state file.

    The running service keeps an in-memory Identity, so stop/start the user
    unit around the edit.  This is user-level only; no system files are touched.
    """
    identity = Identity(cfg.state)
    clients = identity.clients
    if args.list or (not args.all and not args.client):
        if not clients:
            print("No paired devices.")
            return 0
        print("Paired devices:")
        for client_id in clients:
            print(f"  {client_id}")
        if not args.list:
            print("\nRemove one with --client <id> (a unique prefix is enough), "
                  "or remove all with --all.")
        return 0

    if not clients:
        print("No paired devices.")
        return 0

    if args.all:
        targets = list(clients)
    else:
        prefix = args.client.strip().lower()
        targets = [client for client in clients if client.lower().startswith(prefix)]
        if len(targets) != 1:
            print(f"Client prefix {args.client!r} matches {len(targets)} device(s); be more specific.")
            return 1

    service = "apple-tv-remote.service"
    was_active = _run(["systemctl", "--user", "is-active", service])[1] == "active"
    if was_active and args.no_service:
        print("warning: the service is active; stop it first or the in-memory state may overwrite this edit.")
    if was_active and not args.no_service:
        rc, out = _run(["systemctl", "--user", "stop", service])
        if rc != 0:
            print(f"Could not stop {service}: {out}\nStop it manually and rerun with --no-service.")
            return 1

    # Re-read after stopping so we do not overwrite a pairing saved in between.
    identity = Identity(cfg.state)
    removed = [client for client in targets if client in identity.clients]
    for client in removed:
        identity.clients.pop(client, None)
    identity.save()

    if was_active and not args.no_service:
        rc, out = _run(["systemctl", "--user", "start", service])
        if rc != 0:
            print(f"Removed {len(removed)} device(s), but failed to restart {service}: {out}")
            return 1

    PairingGate(_pairing_path(cfg), cfg.pairing_window).touch()
    print(f"Removed {len(removed)} paired device(s). The pairing window is open; "
          "select the device on the iPhone to pair again.")
    return 0


def cmd_doctor(args, cfg: Config) -> int:
    print(f"Apple TV Remote bridge {__version__}")
    distro = _os_release()
    if distro:
        print(f"distro:  {distro} (packages: {_package_manager()})")
    session = " ".join(
        filter(
            None,
            (
                os.environ.get("XDG_SESSION_TYPE"),
                os.environ.get("XDG_CURRENT_DESKTOP"),
                os.environ.get("DESKTOP_SESSION"),
            ),
        )
    )
    if session:
        print(f"session: {session}")
    print(f"config:  {cfg.config_path}")
    print(f"state:   {cfg.state}")
    print(f"backend: {cfg.backend}")
    print(f"device:  {cfg.device_name}")
    print(f"name:    {cfg.name}")

    if cfg.state.exists():
        try:
            identity = Identity(cfg.state)
            print(f"paired:  {len(identity.clients)} device(s)")
        except Exception as exc:  # noqa: BLE001
            print(f"paired:  cannot read state: {exc}")
    else:
        print("paired:  0 devices (state file not created yet)")

    gate = PairingGate(_pairing_path(cfg), cfg.pairing_window)
    age = gate.age()
    print(
        "pairing: "
        + (f"window open ({age:.0f}s old)" if age is not None and gate.allowed() else "window closed")
    )

    if cfg.backend == "uinput":
        ok, message = uinput_status()
        print(f"uinput:  {'OK' if ok else 'NOT READY'}: {message}")
    else:
        print("uinput:  not used by this backend")

    adapters = cec_adapters()
    policy = find_policy(cfg.cec.policy)
    adapter = adapters[0] if adapters else "none"
    writable = "yes" if adapters and os.access(adapters[0], os.W_OK) else "no"
    print(
        f"cec:     enabled={str(cfg.cec.enabled).lower()} policy={policy or 'not found'} "
        f"adapter={adapter} writable={writable}"
    )
    if not cfg.cec.enabled and policy and adapters and writable == "yes":
        print(
            "         CEC is available but disabled; enable with --cec or "
            "[cec].enabled = true."
        )

    gui = PinDisplay(enabled=cfg.pin_display in ("auto", "qt"))
    print(
        f"pin display: mode={cfg.pin_display} gui={'yes' if gui.available() else 'no'} "
        f"notification={'yes' if notification_available() else 'no'}"
    )
    print(
        f"pin gui: mode={choose_mode()} python={gui.python or 'not found'}"
    )
    if cfg.pin_display in ("auto", "qt") and not gui.available():
        print(
            "         install PySide6 (python3-pyside6 / python3-pyside6.qml / pyside6)\n"
            "         and layer-shell-qt on KDE Wayland; or set\n"
            "         pin_display = \"notification\" (needs notify-send). The PIN\n"
            "         is always in the journal and with 'atv-remote pin'."
        )
    if cfg.pin_display == "notification" and not notification_available():
        print(
            "         pin_display = \"notification\" but notify-send was not found;\n"
            "         install libnotify, or use the journal / 'atv-remote pin'."
        )
    if cfg.pin_display in ("auto", "qt") and blur_ignores_region():
        card_radius = detect_corner_radius()
        blur_radius = blur_corner_radius()
        if blur_radius is not None and blur_radius < card_radius:
            print(
                f"pin blur: force-blur effect has CornerRadius={blur_radius}; "
                f"the card uses {card_radius}."
            )
            print(
                "         Run 'atv-remote match-blur-corners' to set it, "
                "or use KWin's built-in blur, for rounded card blur."
            )

    print(f"address: {cfg.address or local_ip()} (auto-detected)")

    for name in ("playerctl", "wpctl", "pactl"):
        print(f"{name:8} {shutil.which(name) or 'not found'}")

    for line in _firewall_note():
        print(line)

    _rc, service = _run(["systemctl", "--user", "is-active", "apple-tv-remote.service"])
    print(f"service: {service or 'unknown'}")

    print("\nIf the iPhone cannot see the bridge:")
    print("  - phone and Fedora must be on the same LAN (not guest Wi-Fi / VLAN)")
    print("  - allow mDNS in firewalld (see above)")
    print("  - run 'atv-remote run -v' in the foreground and inspect the log")
    return 0


def _replace_kwin_corner_radius(path: Path, section: str, value: int) -> bool:
    """Surgically update CornerRadius, preserving the rest of kwinrc."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        lines = []
    out: list[str] = []
    in_section = False
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section and not replaced:
                out.append(f"CornerRadius={value}\n")
                replaced = True
            in_section = stripped == f"[{section}]"
        if in_section and not replaced and stripped.lower().startswith("cornerradius"):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}CornerRadius={value}\n")
            replaced = True
            continue
        out.append(line)
    if in_section and not replaced:
        out.append(f"CornerRadius={value}\n")
        replaced = True
    if not replaced:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(f"\n[{section}]\nCornerRadius={value}\n")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(out), encoding="utf-8")
    except OSError:
        return False
    return True


def _reload_kwin() -> bool:
    for command in (
        ["qdbus", "org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"],
        ["qdbus6", "org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"],
        [
            "busctl",
            "--user",
            "call",
            "org.kde.KWin",
            "/KWin",
            "org.kde.KWin",
            "reconfigure",
        ],
    ):
        if not shutil.which(command[0]):
            continue
        rc, _ = _run(command)
        if rc == 0:
            return True
    return False


def cmd_match_blur_corners(args, cfg: Config) -> int:
    """Opt in to matching Better Blur DX/Blur Plus' corner radius to the card."""
    setting = blur_corner_setting()
    if setting is None:
        print("No Better Blur DX / Blur Plus CornerRadius setting found in kwinrc.")
        return 1
    section, current = setting
    target = detect_corner_radius()
    if current == target:
        print(f"[{section}] CornerRadius is already {target}.")
        return 0
    if args.dry_run:
        print(f"Would set [{section}] CornerRadius {current} -> {target}.")
        return 0

    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    path = config_home / "kwinrc"
    backup = path.with_name(path.name + ".bak-apple-tv-remote")
    if path.is_file() and not backup.exists():
        try:
            shutil.copy2(path, backup)
            print(f"Backup: {backup}")
        except OSError as exc:
            print(f"warning: could not back up {path}: {exc}")

    kwrite = shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")
    written = False
    if kwrite:
        rc, _ = _run(
            [kwrite, "--file", "kwinrc", "--group", section, "--key", "CornerRadius", str(target)]
        )
        written = rc == 0
    if not written:
        written = _replace_kwin_corner_radius(path, section, target)
    if not written:
        print(f"Could not update {path}.")
        return 1

    print(f"Set [{section}] CornerRadius = {target}.")
    if _reload_kwin():
        print("KWin reloaded.")
    else:
        print("Restart KWin or log in again to apply.")
    return 0


# ---------------------------------------------------------------------------
# config / keys


def cmd_config_init(args, cfg: Config) -> int:
    cec = CecConfig(
        enabled=args.cec,
        policy=cfg.cec.policy,
        volume=cfg.cec.volume,
        mute=cfg.cec.mute,
        power_on=cfg.cec.power_on,
        timeout=cfg.cec.timeout,
    )
    target = write_default_config(
        cfg.config_path,
        name=args.name,
        port=args.port if args.port is not None else cfg.port,
        address=args.address,
        backend=args.backend or cfg.backend,
        pairing_window=(
            args.pairing_window if args.pairing_window is not None else cfg.pairing_window
        ),
        pin_display=args.pin_display,
        cec=cec,
        force=args.force,
    )
    print(target)
    return 0


def cmd_config_show(args, cfg: Config) -> int:
    path = cfg.config_path or default_config_path()
    if path.exists():
        print(path.read_text(encoding="utf-8"))
    else:
        print(f"# {path} does not exist; using defaults\n")
        print(
            config_text(
                name=cfg.name,
                port=cfg.port,
                address=cfg.address,
                backend=cfg.backend,
                pairing_window=cfg.pairing_window,
                keymap=cfg.keymap,
                cec=cfg.cec,
                pin_display=cfg.pin_display,
            )
        )
    return 0


def cmd_keys(args, cfg: Config) -> int:
    from .keymap import resolve_key_name

    for action, key_name in cfg.keymap.items():
        if key_name == "auto":
            print(f"{action:12} -> auto ({resolve_key_name(action, key_name)} in this session)")
        else:
            print(f"{action:12} -> {key_name}")
    return 0


# ---------------------------------------------------------------------------
# argument parsing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atv-remote",
        description="Control Linux media/navigation with the iPhone's Apple TV Remote.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="config file (default: ~/.config/apple-tv-remote/config.toml)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    parser.add_argument("--version", action="version", version=__version__)

    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="advertise as an Apple TV and serve the remote")
    run.add_argument("--name", help="name shown on the iPhone")
    run.add_argument("--address", help="IPv4 address to advertise (default: auto)")
    run.add_argument("--port", type=int, help="TCP port (0 = random)")
    run.add_argument("--backend", choices=("uinput", "mpris", "log"), help="output backend")
    run.add_argument("--device-name", help="virtual keyboard name (default: Apple TV Remote Bridge)")
    run.add_argument("--pairing-window", type=int, help="seconds a new pairing is accepted")
    run.add_argument("--state", type=Path, help="identity/pairing state file")

    sub.add_parser("pair", help="open the pairing window for a new phone")
    sub.add_parser("pin", help="print the most recent pairing PIN")
    unpair = sub.add_parser("unpair", help="remove paired phone key(s)")
    unpair.add_argument("--all", action="store_true", help="remove every paired device")
    unpair.add_argument("--client", help="client id (or unique prefix) to remove")
    unpair.add_argument("--list", action="store_true", help="list paired device ids")
    unpair.add_argument("--no-service", action="store_true",
                        help="do not stop/start the user service (stop it yourself first)")
    preview = sub.add_parser("preview-pin", help="show the PIN card for design/testing")
    preview.add_argument("--pin", default="1234")
    preview.add_argument("--seconds", type=int, default=8)
    sub.add_parser("doctor", help="check permissions, firewall, service and state")
    blur = sub.add_parser(
        "match-blur-corners",
        help="set Better Blur DX/Blur Plus corner radius to the PIN card radius",
    )
    blur.add_argument("--dry-run", action="store_true", help="show the change only")
    sub.add_parser("keys", help="show the action -> Linux key mapping")

    config = sub.add_parser("config", help="inspect or create the config file")
    config_sub = config.add_subparsers(dest="config_command")
    init = config_sub.add_parser("init", help="write a commented default config")
    init.add_argument("--name")
    init.add_argument("--port", type=int)
    init.add_argument("--address", help="IPv4 address to advertise")
    init.add_argument("--backend", choices=("uinput", "mpris", "log"))
    init.add_argument("--pairing-window", type=int)
    init.add_argument("--cec", dest="cec", action="store_true",
                      help="enable HDMI-CEC volume/mute/TV-on (opt-in)")
    init.add_argument("--no-cec", dest="cec", action="store_false",
                      help="disable HDMI-CEC (default)")
    init.add_argument(
        "--pin-display",
        choices=("auto", "qt", "notification", "none"),
        default="auto",
        help="PIN presentation: auto (GUI if available), qt, notification, or none",
    )
    init.add_argument("--force", action="store_true", help="overwrite an existing config")
    init.set_defaults(cec=False)
    config_sub.add_parser("show", help="print the config file or defaults")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2

    configure_logging(args.verbose)
    try:
        cfg = load_config(args.config)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.command == "run":
        return cmd_run(args, cfg)
    if args.command == "pair":
        return cmd_pair(args, cfg)
    if args.command == "pin":
        return cmd_pin(args, cfg)
    if args.command == "unpair":
        return cmd_unpair(args, cfg)
    if args.command == "preview-pin":
        return cmd_preview_pin(args, cfg)
    if args.command == "doctor":
        return cmd_doctor(args, cfg)
    if args.command == "match-blur-corners":
        return cmd_match_blur_corners(args, cfg)
    if args.command == "keys":
        return cmd_keys(args, cfg)
    if args.command == "config":
        if args.config_command == "init":
            return cmd_config_init(args, cfg)
        if args.config_command == "show":
            return cmd_config_show(args, cfg)
        parser.parse_args(["config", "--help"])
        return 2
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
