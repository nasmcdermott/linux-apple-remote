"""Configuration handling for the Apple TV Remote bridge.

Everything lives under the user's XDG config directory; nothing here touches
system-wide paths.  The config file is optional -- defaults are used until the
user runs ``atv-remote config init`` or edits the generated file.
"""

from __future__ import annotations

import json
import os
import socket
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .cec import CecConfig
from .keymap import DEFAULT_KEYMAP, validate_keymap

APP_DIR = "apple-tv-remote"
BACKENDS = ("uinput", "mpris", "log")


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / APP_DIR


def default_config_path() -> Path:
    return config_dir() / "config.toml"


def default_state_path() -> Path:
    return config_dir() / "state.json"


@dataclass
class Config:
    name: str = field(default_factory=socket.gethostname)
    port: int = 47832
    address: str | None = None
    backend: str = "uinput"
    device_name: str = "Apple TV Remote Bridge"
    pairing_window: int = 600
    state: Path = field(default_factory=default_state_path)
    keymap: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_KEYMAP))
    cec: CecConfig = field(default_factory=CecConfig)
    pin_display: str = "auto"
    config_path: Path | None = None

    def validate(self) -> None:
        self.backend = self.backend.lower().strip()
        if self.backend not in BACKENDS:
            raise ValueError(f"backend must be one of {', '.join(BACKENDS)}, not {self.backend!r}")
        if not 0 <= int(self.port) <= 65535:
            raise ValueError(f"port must be 0-65535, not {self.port!r}")
        if int(self.pairing_window) < 0:
            raise ValueError("pairing_window must be >= 0 seconds")
        if not self.name.strip():
            raise ValueError("name must not be empty")
        self.pin_display = self.pin_display.lower().strip()
        if self.pin_display not in ("auto", "qt", "notification", "none"):
            raise ValueError("pin_display must be auto, qt, notification or none")
        self.keymap = validate_keymap(self.keymap)
        self.cec.validate()


def load_config(path: Path | str | None = None) -> Config:
    """Load ``config.toml`` if present, else return defaults."""
    config_path = Path(path).expanduser() if path else default_config_path()
    cfg = Config(config_path=config_path)

    if not config_path.exists():
        # A custom --config should keep its identity next to the config.
        cfg.state = config_path.parent / "state.json"
        cfg.validate()
        return cfg

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    remote = data.get("remote", {})
    if not isinstance(remote, dict):
        raise TypeError("[remote] must be a TOML table")

    if "name" in remote:
        cfg.name = str(remote["name"])
    if "port" in remote:
        cfg.port = int(remote["port"])
    if "address" in remote:
        cfg.address = str(remote["address"]) or None
    if "backend" in remote:
        cfg.backend = str(remote["backend"])
    if "device_name" in remote:
        cfg.device_name = str(remote["device_name"])
    if "pairing_window" in remote:
        cfg.pairing_window = int(remote["pairing_window"])
    if "pin_display" in remote:
        cfg.pin_display = str(remote["pin_display"])
    if "state" in remote:
        state = Path(str(remote["state"])).expanduser()
        if not state.is_absolute():
            state = config_path.parent / state
        cfg.state = state
    else:
        # Keep state next to the config so a custom --config is self-contained.
        cfg.state = config_path.parent / "state.json"

    keys = data.get("keys", {})
    if not isinstance(keys, dict):
        raise TypeError("[keys] must be a TOML table")
    for action, key_name in keys.items():
        if action in DEFAULT_KEYMAP:
            cfg.keymap[action] = str(key_name)

    cec = data.get("cec", {})
    if not isinstance(cec, dict):
        raise TypeError("[cec] must be a TOML table")
    if "enabled" in cec:
        cfg.cec.enabled = bool(cec["enabled"])
    if "policy" in cec:
        cfg.cec.policy = str(cec["policy"])
    if "volume" in cec:
        cfg.cec.volume = bool(cec["volume"])
    if "mute" in cec:
        cfg.cec.mute = bool(cec["mute"])
    if "power_on" in cec:
        cfg.cec.power_on = bool(cec["power_on"])
    if "timeout" in cec:
        cfg.cec.timeout = int(cec["timeout"])

    cfg.validate()
    return cfg


def config_text(
    *,
    name: str | None = None,
    port: int = 47832,
    address: str | None = None,
    backend: str = "uinput",
    pairing_window: int = 600,
    keymap: dict[str, str] | None = None,
    cec: CecConfig | None = None,
    pin_display: str = "auto",
) -> str:
    """Render a config file with comments and the current defaults."""
    mapping = dict(DEFAULT_KEYMAP)
    if keymap:
        mapping.update(keymap)
    lines = [
        "# Apple TV Remote bridge configuration",
        "# Edit, then restart: systemctl --user restart apple-tv-remote",
        "",
        "[remote]",
        f"name = {json.dumps(name or socket.gethostname())}",
        f"port = {int(port)}",
        'backend = ' + json.dumps(backend),
        'device_name = "Apple TV Remote Bridge"',
        f"pairing_window = {int(pairing_window)}",
        f'pin_display = {json.dumps(pin_display)}   # auto | qt | notification | none',
        (
            f"address = {json.dumps(address)}"
            if address
            else '# address = "192.168.1.50"   # uncomment if auto-detection picks the wrong interface'
        ),
        "",
        "[keys]",
        "# Action -> Linux input key name, or a special action.",
        "# bigscreen_overlay opens Plasma Bigscreen's Home/Search/Tasks overlay",
        "# via the same D-Bus call the Fire TV remote uses.",
        "# Remove a line to make that button do nothing.",
    ]
    for action in DEFAULT_KEYMAP:
        lines.append(f"{action} = {json.dumps(mapping[action])}")
    cec_cfg = cec or CecConfig()
    lines.extend(
        [
            "",
            "[cec]",
            "# CEC is opt-in: it needs cec-policy plus a writable /dev/cec*.",
            "# Enable with './install.sh --cec' or set enabled = true.",
            "# When enabled, volume/mute go to the same cec-policy script as the",
            "# Fire remote; when disabled, the ordinary media keys are used.",
            f"enabled = {'true' if cec_cfg.enabled else 'false'}",
            f"policy = {json.dumps(cec_cfg.policy)}",
            f"volume = {'true' if cec_cfg.volume else 'false'}",
            f"mute = {'true' if cec_cfg.mute else 'false'}",
            "# Power always sends KEY_POWER (the desktop menu); power_on adds the",
            "# CEC TV-on sequence: cec-policy wake --reason powerkey.",
            f"power_on = {'true' if cec_cfg.power_on else 'false'}",
            f"timeout = {int(cec_cfg.timeout)}",
        ]
    )
    lines.append("")
    return "\n".join(lines)


def write_default_config(
    path: Path | str | None = None,
    *,
    name: str | None = None,
    port: int = 47832,
    address: str | None = None,
    backend: str = "uinput",
    pairing_window: int = 600,
    pin_display: str = "auto",
    cec: CecConfig | None = None,
    force: bool = False,
) -> Path:
    """Create the config file.  Returns the path.  Does not overwrite unless ``force``."""
    target = Path(path).expanduser() if path else default_config_path()
    if target.exists() and not force:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        config_text(
            name=name,
            port=port,
            address=address,
            backend=backend,
            pairing_window=pairing_window,
            pin_display=pin_display,
            cec=cec,
        ),
        encoding="utf-8",
    )
    target.chmod(0o644)
    return target
