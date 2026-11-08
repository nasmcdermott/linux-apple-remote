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
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class Palette:
    background: str
    foreground: str
    accent: str
    font_family: str
    is_dark: bool
    font_scale: float = 1.0
    has_blur: bool = False
    corner_radius: int = 24
    cell: str = "#1f1f1f"
    cell_foreground: str = "#ffffff"
    muted: str = "#a0a0a0"


DEFAULT_DARK = Palette("#141414", "#ffffff", "#4a90d9", "Noto Sans", True)
DEFAULT_LIGHT = Palette(
    "#f6f5f4",
    "#1d1d1d",
    "#3584e4",
    "Noto Sans",
    False,
    cell="#ffffff",
    cell_foreground="#1d1d1d",
    muted="#5f5f5f",
)
BASE_POINT_SIZE = 10.0
MIN_FONT_SCALE = 0.85
MAX_FONT_SCALE = 1.6
MAX_CORNER_RADIUS = 40

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


def _kwinrc_parser() -> configparser.RawConfigParser | None:
    """Read the user's KWin config if it exists (KDE only)."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or _home() / ".config")
    path = config_home / "kwinrc"
    if not path.is_file():
        return None
    parser = configparser.RawConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    try:
        parser.read(path, encoding="utf-8")
    except (OSError, configparser.Error):
        return None
    return parser


def _font_scale(points: float) -> float:
    """Turn a desktop font point size into a layout multiplier."""
    if not points or points <= 0:
        return 1.0
    return max(MIN_FONT_SCALE, min(MAX_FONT_SCALE, points / BASE_POINT_SIZE))


def _kde_font(value: str) -> tuple[str, float]:
    """Parse KDE's ``family,pointsize,...`` font string."""
    parts = [part.strip() for part in value.split(",")]
    family = parts[0] if parts and parts[0] else "Noto Sans"
    points = BASE_POINT_SIZE
    if len(parts) > 1:
        try:
            points = float(parts[1])
        except ValueError:
            pass
    return family, _font_scale(points)


def _gnome_font(value: str) -> tuple[str, float]:
    """Parse GNOME's ``family point`` font string."""
    parts = value.split()
    points = BASE_POINT_SIZE
    if parts:
        try:
            points = float(parts[-1])
            parts = parts[:-1]
        except ValueError:
            pass
    family = " ".join(parts) or "Noto Sans"
    return family, _font_scale(points)


def detect_blur() -> bool:
    """True when KWin has any blur/glass effect enabled for normal windows.

    The PIN card is a translucent surface: the compositor does the actual
    backdrop blur.  Better Blur DX, Force Blur, Blur Plus and Liquid Glass all
    register themselves in ``[Plugins]`` as ``<name>Enabled=true``.
    """
    parser = _kwinrc_parser()
    if parser is None or not parser.has_section("Plugins"):
        return False
    for key, value in parser.items("Plugins"):
        name = key.lower()
        if not name.endswith("enabled"):
            continue
        if "blur" not in name and "glass" not in name:
            continue
        if value.strip().lower() in ("true", "1", "yes", "on"):
            return True
    return False


def blur_ignores_region() -> bool:
    """True for blur effects that blur the whole window and ignore app regions.

    Better Blur DX, Force Blur, Blur Plus and Liquid Glass are written as
    "force blur" effects: they blur the window's square geometry and apply
    their own corner radius.  The card requests a rounded blur region, but
    those effects ignore it, so a normal window (rounded by ShapeCorners) is a
    better fit than a layer-shell surface.
    """
    parser = _kwinrc_parser()
    if parser is None or not parser.has_section("Plugins"):
        return False
    for key, value in parser.items("Plugins"):
        name = key.lower()
        if not name.endswith("enabled"):
            continue
        if value.strip().lower() not in ("true", "1", "yes", "on"):
            continue
        if any(
            effect in name
            for effect in (
                "better_blur_dx",
                "forceblur",
                "blurplus",
                "liquidglass",
                "glass",
            )
        ):
            return True
    return False


def blur_corner_setting() -> tuple[str, int] | None:
    """Return the force-blur effect's ``(section, corner radius)``, if any."""
    parser = _kwinrc_parser()
    if parser is None:
        return None
    for section, key in (
        ("Effect-better-blur-dx", "CornerRadius"),
        ("Effect-blurplus", "CornerRadius"),
    ):
        if not parser.has_section(section) or not parser.has_option(section, key):
            continue
        try:
            return section, int(float(parser.get(section, key)))
        except (TypeError, ValueError):
            return None
    return None


def blur_corner_radius() -> int | None:
    """Return a force-blur effect's configured corner radius, if any."""
    setting = blur_corner_setting()
    return setting[1] if setting else None


def detect_corner_radius(default: int = 24) -> int:
    """Read the compositor's rounded-corner radius so blur matches the card.

    KWin effects disagree on the key name, so try the common ones.  Values
    outside a sane range (and the tiny blur-texture radius some effects use)
    are ignored.
    """
    parser = _kwinrc_parser()
    if parser is None:
        return default
    candidates = (
        ("ShapeCorners", "Roundness"),
        ("ShapeCorners", "Radius"),
        ("Round-Corners", "InactiveCornerRadius"),
        ("Round-Corners", "WindowCornerRadius"),
        ("Effect-liquidglass", "WindowCornerRadius"),
        ("Effect-blurplus", "TopCornerRadius"),
    )
    for section, key in candidates:
        if not parser.has_section(section) or not parser.has_option(section, key):
            continue
        try:
            value = int(float(parser.get(section, key)))
        except (TypeError, ValueError):
            continue
        if 8 <= value <= MAX_CORNER_RADIUS:
            return value
    return default


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
        cell = parse_color(_get(parser, "Colors:Button", "BackgroundNormal"), background)
        cell_foreground = parse_color(
            _get(parser, "Colors:Button", "ForegroundNormal"), foreground
        )
        muted = parse_color(_get(parser, "Colors:Window", "ForegroundInactive"), foreground)
        font, font_scale = _kde_font(_get(parser, "General", "font") or "")
        return Palette(
            background,
            foreground,
            accent,
            font,
            is_dark_color(background),
            font_scale,
            cell=cell,
            cell_foreground=cell_foreground,
            muted=muted,
        )
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
    if font_value:
        font, font_scale = _gnome_font(font_value)
    else:
        font, font_scale = base.font_family, 1.0

    return Palette(
        base.background,
        base.foreground,
        accent,
        font,
        dark,
        font_scale,
        cell=base.cell,
        cell_foreground=base.cell_foreground,
        muted=base.muted,
    )


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
            return replace(
                kde,
                has_blur=detect_blur(),
                corner_radius=detect_corner_radius(),
            )
    if "gnome" in desktop or "ubuntu" in desktop:
        return _read_gnome()
    return DEFAULT_DARK
