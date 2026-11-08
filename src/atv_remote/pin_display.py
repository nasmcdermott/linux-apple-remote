"""Launch the Qt Quick pairing-PIN card, with a graceful fallback.

The daemon itself stays dependency-free; the GUI runs in a separate process
using the system Python that has PySide6.  On KDE Wayland the card is a
layer-shell surface anchored to the top-right; on GNOME Wayland it is a
transparent full-screen overlay with the card in the same corner; on X11 it is
a small window positioned at the top-right.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .palette import Palette, detect_palette

_LOGGER = logging.getLogger(__name__)

QML_DIR = Path(__file__).resolve().parent / "qml"
GUI_SCRIPT = Path(__file__).resolve().with_name("pin_gui.py")


def _qml_roots() -> list[Path]:
    """Qt QML import roots, including multiarch distro layouts."""
    roots: list[Path] = []
    for variable in ("QML2_IMPORT_PATH", "QML_IMPORT_PATH"):
        for entry in os.environ.get(variable, "").split(os.pathsep):
            if entry:
                roots.append(Path(entry))
    roots.extend(
        Path(path)
        for path in (
            "/usr/lib64/qt6/qml",
            "/usr/lib/qt6/qml",
            "/usr/local/lib64/qt6/qml",
            "/usr/local/lib/qt6/qml",
        )
    )
    # Debian/Ubuntu use /usr/lib/<triplet>/qt6/qml; this also covers other
    # architectures and distros that use a similar layout.
    for base in ("/usr/lib", "/usr/local/lib"):
        roots.extend(Path(base).glob("*/qt6/qml"))
    return roots


def layer_shell_available() -> bool:
    seen: set[str] = set()
    for root in _qml_roots():
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        if (root / "org/kde/layershell").is_dir():
            return True
    return False


def find_gui_python() -> str | None:
    """Find a Python that can import PySide6 (usually the system Python)."""
    candidates = [
        os.environ.get("ATV_PIN_GUI_PYTHON"),
        "/usr/bin/python3",
        shutil.which("python3"),
        sys.executable,
    ]
    for candidate in dict.fromkeys(c for c in candidates if c):
        if not Path(candidate).exists():
            continue
        try:
            result = subprocess.run(
                [candidate, "-c", "import PySide6"],
                capture_output=True,
                timeout=4,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return candidate
    return None


def choose_mode(env: dict[str, str] | None = None) -> str:
    env = env or os.environ
    session = env.get("XDG_SESSION_TYPE", "").lower()
    if not session:
        session = "wayland" if env.get("WAYLAND_DISPLAY") else "x11"
    desktop = " ".join(
        filter(
            None,
            (
                env.get("XDG_CURRENT_DESKTOP", ""),
                env.get("DESKTOP_SESSION", ""),
                env.get("KDE_FULL_SESSION", ""),
            ),
        )
    ).lower()

    if session == "wayland":
        if "kde" in desktop:
            # Layer-shell gives the true top-right overlay.  Match the blur
            # effect's corner radius with 'atv-remote match-blur-corners'
            # rather than dropping to a normal window (which loses the layer).
            return "layer" if layer_shell_available() else "window"
        if (
            ("sway" in desktop or "hyprland" in desktop)
            and layer_shell_available()
        ):
            return "layer"
        if "gnome" in desktop or "ubuntu" in desktop:
            return "fullscreen"
        return "window"
    return "window"


class PinDisplay:
    """Owns at most one short-lived PIN window process."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.python = find_gui_python() if enabled else None
        self.proc: subprocess.Popen | None = None

    def available(self) -> bool:
        return bool(
            self.enabled
            and self.python
            and (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))
            and GUI_SCRIPT.is_file()
            and (QML_DIR / "PinCard.qml").is_file()
        )

    def show(self, pin: str, ttl: int) -> bool:
        if not self.available():
            return False
        self.clear()
        palette: Palette = detect_palette()
        mode = choose_mode()
        command = [
            self.python or "/usr/bin/python3",
            str(GUI_SCRIPT),
            "--pin",
            pin,
            "--ttl",
            str(max(1, int(ttl))),
            "--mode",
            mode,
            "--bg",
            palette.background,
            "--fg",
            palette.foreground,
            "--cell",
            palette.cell,
            "--cell-fg",
            palette.cell_foreground,
            "--muted",
            palette.muted,
            "--accent",
            palette.accent,
            "--font",
            palette.font_family,
            "--dark",
            "1" if palette.is_dark else "0",
            "--font-scale",
            f"{palette.font_scale:.2f}",
            "--blur",
            "1" if palette.has_blur else "0",
            "--corner-radius",
            str(palette.corner_radius),
        ]
        try:
            self.proc = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            _LOGGER.warning("PIN GUI failed to start: %s", exc)
            self.proc = None
            return False
        _LOGGER.info(
            "PIN GUI shown (mode=%s, palette=%s, blur=%s, scale=%.2f)",
            mode,
            palette.background,
            palette.has_blur,
            palette.font_scale,
        )
        return True

    def clear(self) -> None:
        proc, self.proc = self.proc, None
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            try:
                proc.kill()
            except OSError:
                pass

    def close(self) -> None:
        self.clear()
