"""Output backends: turn semantic actions into real desktop input.

* ``uinput`` -- the real thing: a virtual Linux keyboard.  Works on Wayland,
  X11, KDE, GNOME and even a TTY, because it sits below the display server.
* ``mpris``  -- no /dev/uinput access needed, but only media/volume actions.
* ``log``    -- dry run; prints actions and injects nothing.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time

from evdev import UInput, ecodes

from .cec import CecConfig, CecOutput, CecPolicy
from .keymap import SPECIAL_KEYS, code_for, is_bigscreen_session, resolve_key_name

_LOGGER = logging.getLogger(__name__)


class OutputError(RuntimeError):
    """Raised when the requested output backend cannot start."""


class Output:
    name = "output"

    def press(self, action: str) -> bool:
        raise NotImplementedError

    def hold(self, action: str) -> bool:
        """Start holding a key down.  Backends that cannot hold return False.

        A False return tells the server to fall back to a normal tap on
        release, so long-press is optional and never loses the button.
        """
        return False

    def release(self, action: str) -> bool:
        """Finish a hold.  The default is a normal tap for non-key backends."""
        return self.press(action)

    def close(self) -> None:
        pass


class UInputOutput(Output):
    name = "uinput"

    def __init__(self, keymap: dict[str, str], device_name: str = "Apple TV Remote Bridge") -> None:
        self._codes: dict[str, int] = {}
        self._specials: dict[str, str] = {}
        for action, key in keymap.items():
            resolved = resolve_key_name(action, key)
            if resolved in SPECIAL_KEYS:
                self._specials[action] = resolved
            else:
                self._codes[action] = code_for(resolved)

        codes = set(self._codes.values())
        if "bigscreen_overlay" in self._specials.values():
            # Fallback when the Plasma D-Bus call is unavailable.
            codes.add(ecodes.KEY_MENU)
        self._held: int | None = None
        capabilities = {ecodes.EV_KEY: sorted(codes)}
        try:
            self.ui = UInput(
                capabilities,
                name=device_name,
                bustype=ecodes.BUS_VIRTUAL,
                vendor=0x1D6B,
                product=0x0101,
                version=0x0001,
            )
        except PermissionError as exc:
            raise OutputError(
                "cannot open /dev/uinput (permission denied).\n"
                "  * check:  test -w /dev/uinput && echo writable\n"
                "  * temporary ACL:  sudo setfacl -m u:$USER:rw /dev/uinput\n"
                "  * or run the daemon with sudo\n"
                "  * or use --backend mpris for media-only control"
            ) from exc
        except OSError as exc:
            raise OutputError(
                f"cannot create a virtual keyboard: {exc}\n"
                "  Is the uinput module loaded?  Try: sudo modprobe uinput"
            ) from exc

    @property
    def device_path(self) -> str:
        return getattr(getattr(self.ui, "device", None), "path", "")

    def _write_key(self, code: int, value: int) -> None:
        self.ui.write(ecodes.EV_KEY, code, value)
        self.ui.syn()

    def _tap_code(self, code: int) -> bool:
        self._write_key(code, 1)
        # A short hold is friendlier to apps that debounce keys.
        time.sleep(0.02)
        self._write_key(code, 0)
        return True

    def _plasma_overlay(self) -> bool:
        """Open the Plasma Bigscreen home overlay via plasmashell's D-Bus API.

        This is the same call the Fire TV remote's Menu button uses; it is more
        reliable than a key binding, which users can rebind or remove.
        ``busctl`` is preferred (systemd distros); ``gdbus`` and ``dbus-send``
        keep the same action working on non-systemd and minimal installs.
        """
        commands: list[list[str]] = []
        busctl = shutil.which("busctl")
        if busctl:
            commands.append(
                [
                    busctl,
                    "--user",
                    "call",
                    "org.kde.plasmashell",
                    "/PlasmaShell",
                    "org.kde.PlasmaShell",
                    "activateLauncherMenu",
                ]
            )
        gdbus = shutil.which("gdbus")
        if gdbus:
            commands.append(
                [
                    gdbus,
                    "call",
                    "--session",
                    "--dest",
                    "org.kde.plasmashell",
                    "--object-path",
                    "/PlasmaShell",
                    "--method",
                    "org.kde.PlasmaShell.activateLauncherMenu",
                ]
            )
        dbus_send = shutil.which("dbus-send")
        if dbus_send:
            commands.append(
                [
                    dbus_send,
                    "--session",
                    "--dest=org.kde.plasmashell",
                    "--type=method_call",
                    "/PlasmaShell",
                    "org.kde.PlasmaShell.activateLauncherMenu",
                ]
            )

        for command in commands:
            try:
                result = subprocess.run(
                    command, capture_output=True, timeout=5, check=False
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                _LOGGER.debug("%s failed: %s", command[0], exc)
                continue
            if result.returncode == 0:
                return True
            _LOGGER.debug(
                "%s rc=%s: %s",
                command[0],
                result.returncode,
                result.stderr.decode("utf-8", "replace").strip(),
            )
        return False

    def _special(self, action: str) -> bool:
        name = self._specials[action]
        if name == "bigscreen_overlay":
            if is_bigscreen_session() and self._plasma_overlay():
                return True
            return self._tap_code(ecodes.KEY_MENU)
        _LOGGER.warning("unknown special action %r for %s", name, action)
        return False

    def press(self, action: str) -> bool:
        if action in self._specials:
            return self._special(action)
        code = self._codes.get(action)
        if code is None:
            return False
        return self._tap_code(code)

    def hold(self, action: str) -> bool:
        code = self._codes.get(action)
        if code is None:
            return False
        if self._held is not None and self._held != code:
            self._write_key(self._held, 0)
        self._held = code
        self._write_key(code, 1)
        return True

    def release(self, action: str) -> bool:
        code = self._codes.get(action)
        if code is None:
            return False
        self._write_key(code, 0)
        if self._held == code:
            self._held = None
        return True

    def close(self) -> None:
        if self._held is not None:
            try:
                self._write_key(self._held, 0)
            except Exception as exc:  # noqa: BLE001 - device may already be gone
                _LOGGER.debug("releasing held key on close failed: %s", exc)
            self._held = None
        try:
            self.ui.close()
        except Exception as exc:  # noqa: BLE001 - best effort during shutdown
            _LOGGER.debug("closing virtual keyboard failed: %s", exc)


class MprisOutput(Output):
    """Media-only fallback using playerctl/wpctl (or pactl)."""

    name = "mpris"

    def __init__(self) -> None:
        self._playerctl = shutil.which("playerctl")
        self._wpctl = shutil.which("wpctl")
        self._pactl = shutil.which("pactl")
        if not self._playerctl and not (self._wpctl or self._pactl):
            raise OutputError(
                "mpris backend needs playerctl and wpctl (or pactl). "
                "Install playerctl and wireplumber (or pulseaudio-utils) "
                "with your distro's package manager."
            )

    def press(self, action: str) -> bool:
        command: list[str] | None = None
        if action in ("play_pause", "next", "previous"):
            if not self._playerctl:
                _LOGGER.warning("playerctl is not installed; ignoring %s", action)
                return False
            sub = {"play_pause": "play-pause", "next": "next", "previous": "previous"}[action]
            command = [self._playerctl, sub]
        elif action in ("volume_up", "volume_down", "mute"):
            if self._wpctl:
                if action == "volume_up":
                    command = [self._wpctl, "set-volume", "@DEFAULT_AUDIO_SINK@", "5%+"]
                elif action == "volume_down":
                    command = [self._wpctl, "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-"]
                else:
                    command = [self._wpctl, "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"]
            elif self._pactl:
                if action == "volume_up":
                    command = [self._pactl, "set-sink-volume", "@DEFAULT_SINK@", "+5%"]
                elif action == "volume_down":
                    command = [self._pactl, "set-sink-volume", "@DEFAULT_SINK@", "-5%"]
                else:
                    command = [self._pactl, "set-sink-mute", "@DEFAULT_SINK@", "toggle"]
        else:
            _LOGGER.info("mpris backend ignores navigation action %r (use uinput)", action)
            return False

        if command is None:
            return False
        try:
            subprocess.run(command, check=False, timeout=3, capture_output=True)
            return True
        except (OSError, subprocess.TimeoutExpired) as exc:
            _LOGGER.warning("command failed: %s (%s)", command, exc)
            return False


class LogOutput(Output):
    name = "log"

    def press(self, action: str) -> bool:
        print(f"[action] {action}", flush=True)
        return True


def make_output(
    backend: str,
    keymap: dict[str, str],
    device_name: str = "Apple TV Remote Bridge",
    cec: CecConfig | None = None,
) -> Output | CecOutput:
    backend = backend.lower()
    if backend == "uinput":
        output: Output = UInputOutput(keymap, device_name=device_name)
    elif backend == "mpris":
        output = MprisOutput()
    elif backend == "log":
        output = LogOutput()
    else:
        raise OutputError(f"unknown backend: {backend}")

    if cec and cec.enabled:
        policy = CecPolicy.from_config(cec)
        if policy:
            return CecOutput(output, policy, cec)
    return output


def uinput_status() -> tuple[bool, str]:
    """Check /dev/uinput access without leaving a virtual device behind."""
    if not os.path.exists("/dev/uinput"):
        return False, "/dev/uinput does not exist (load the uinput kernel module?)"
    if not os.access("/dev/uinput", os.W_OK):
        return False, "/dev/uinput is not writable by this user"
    try:
        ui = UInput({ecodes.EV_KEY: [ecodes.KEY_ENTER]}, name="atv-remote doctor")
        ui.close()
    except Exception as exc:  # noqa: BLE001 - report whatever the kernel says
        return False, f"could not create a test virtual keyboard: {exc}"
    return True, "/dev/uinput is writable and a test device was created"
