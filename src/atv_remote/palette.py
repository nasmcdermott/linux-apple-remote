"""Read the host desktop's colors for the pairing-PIN overlay.

KDE is the primary target: the values come straight from ``kdeglobals``
(Window background/foreground and the Selection accent), so the overlay follows
Plasma's color scheme.  GNOME is read through ``gsettings``; other desktops get
a neutral dark glass palette.  No theme engine or extra dependency is needed.
"""

from __future__ import annotations

import configparser
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Palette:
    background: str
    foreground: str
    accent: str
    font_family: str
    is_dark: bool


DEFAULT_DARK = Palette("#141414", "#ffffff", "#4a90d9", "Noto Sans", True)
DEFAULT_LIGHT = Palette("#f6f5f4", "#1d1d1d", "#3584e4", "Noto Sans", False)

_GNOME_ACCENTS = {
    "blue": "#3584e4",
    "teal": "#2190a4",
    "green": "#3a944a",
    "yellow": "#e5a50a",
    "orange": "#ed5b00",
    "red": "#e01b24",
    "pink": "#d56199",
    "purple": "#9141ac",
    "slate": "#6f8396",
}


def _home() -> Path:
    return Path(os.environ.get("HOME") or Path.home())


def _kde_globals_paths() -> list[Path]:
    xdg = Path(os.environ.get("XDG_CONFIG_HOME") or _home() / ".config")
    return [
        xdg / "kdeglobals",
        _home() / ".config" / "kdeglobals",
        _home() / ".config" / "kdedefaults" / "kdeglobals",
        Path("/etc/xdg/kdeglobals"),
    ]


def parse_color(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    value = value.strip()
    if value.startswith("#"):
        if len(value) == 7:
            return value.lower()
        if len(value) == 9:  # #AARRGGBB
            return "#" + value[3:].lower()
        return fallback
    parts = [part.strip() for part in value.split(",")]
    if len(parts) < 3:
        return fallback
    try:
        red, green, blue = (max(0, min(255, int(part))) for part in parts[:3])
    except ValueError:
        return fallback
    return f"#{red:02x}{green:02x}{blue:02x}"


def is_dark_color(hex_color: str) -> bool:
    color = hex_color.lstrip("#")
    try:
        red, green, blue = (int(color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    except (ValueError, IndexError):
        return True
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    return luminance < 0.5


def _get(parser: configparser.RawConfigParser, section: str, key: str, fallback: str = "") -> str:
    try:
        return parser.get(section, key, fallback=fallback)
    except (configparser.Error, KeyError):
        return fallback


def _read_kde() -> Palette | None:
    for path in _kde_globals_paths():
        if not path.is_file():
            continue
        parser = configparser.RawConfigParser(strict=False, interpolation=None)
        parser.optionxform = str
        try:
            parser.read(path, encoding="utf-8")
        except (OSError, configparser.Error):
            continue

        background = parse_color(_get(parser, "Colors:Window", "BackgroundNormal"), "#141414")
        foreground = parse_color(_get(parser, "Colors:Window", "ForegroundNormal"), "#ffffff")
        accent = parse_color(_get(parser, "Colors:Selection", "BackgroundNormal"), "#4a90d9")
        font = (_get(parser, "General", "font") or "").split(",", 1)[0].strip() or "Noto Sans"
        return Palette(background, foreground, accent, font, is_dark_color(background))
    return None


def _gsettings(key: str) -> str | None:
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", key],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip().strip("'")


def _read_gnome() -> Palette:
    scheme = (_gsettings("color-scheme") or "").lower()
    theme = (_gsettings("gtk-theme") or "").lower()
    dark = scheme == "prefer-dark" or (scheme != "prefer-light" and "dark" in theme)
    base = DEFAULT_DARK if dark else DEFAULT_LIGHT

    accent_name = (_gsettings("accent-color") or "").lower()
    if accent_name.startswith("#"):
        accent = accent_name
    else:
        accent = _GNOME_ACCENTS.get(accent_name, base.accent)

    font_value = _gsettings("font-name") or ""
    font_parts = font_value.split()
    if len(font_parts) > 1 and font_parts[-1].isdigit():
        font_parts = font_parts[:-1]
    font = " ".join(font_parts) or base.font_family

    return Palette(base.background, base.foreground, accent, font, dark)


def detect_palette() -> Palette:
    desktop = " ".join(
        filter(
            None,
            (
                os.environ.get("XDG_CURRENT_DESKTOP", ""),
                os.environ.get("DESKTOP_SESSION", ""),
                os.environ.get("KDE_FULL_SESSION", ""),
            ),
        )
    ).lower()
    if "kde" in desktop or os.environ.get("KDE_FULL_SESSION", "").lower() == "true":
        kde = _read_kde()
        if kde:
            return kde
    if "gnome" in desktop or "ubuntu" in desktop:
        return _read_gnome()
    return DEFAULT_DARK
