from __future__ import annotations

from pathlib import Path

from atv_remote.palette import (
    DEFAULT_DARK,
    _font_scale,
    _gnome_font,
    _kde_font,
    blur_corner_radius,
    blur_ignores_region,
    detect_palette,
    is_dark_color,
    parse_color,
)
from atv_remote.pin_display import PinDisplay, choose_mode


def test_parse_color():
    assert parse_color("17,17,17", "#000000") == "#111111"
    assert parse_color("#ABCDEF", "#000000") == "#abcdef"
    assert parse_color("#80abcdef", "#000000") == "#abcdef"
    assert parse_color("not-a-color", "#123456") == "#123456"


def test_is_dark_color():
    assert is_dark_color("#111111") is True
    assert is_dark_color("#f6f5f4") is False


def test_kde_palette_reads_kdeglobals(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("KDE_FULL_SESSION", "true")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    config = tmp_path / ".config" / "kdeglobals"
    config.parent.mkdir(parents=True)
    config.write_text(
        """
[Colors:Window]
BackgroundNormal=17,17,17
ForegroundNormal=255,255,255
ForegroundInactive=160,160,160
[Colors:Selection]
BackgroundNormal=74,144,217
[Colors:Button]
BackgroundNormal=20,20,20
ForegroundNormal=255,255,255
[General]
font=SF Pro Text,10,-1,5,50,0,0,0,0,0
""".strip()
    )
    kwinrc = tmp_path / ".config" / "kwinrc"
    kwinrc.write_text(
        """
[Plugins]
blurEnabled=false
better_blur_dxEnabled=true
[Effect-better-blur-dx]
CornerRadius=2
[Round-Corners]
InactiveCornerRadius=28
""".strip()
    )
    palette = detect_palette()
    assert palette.background == "#111111"
    assert palette.foreground == "#ffffff"
    assert palette.accent == "#4a90d9"
    assert palette.font_family == "SF Pro Text"
    assert palette.is_dark is True
    assert palette.font_scale == 1.0
    assert palette.has_blur is True
    assert palette.corner_radius == 28
    assert palette.cell == "#141414"
    assert palette.cell_foreground == "#ffffff"
    assert palette.muted == "#a0a0a0"
    assert blur_ignores_region() is True
    assert blur_corner_radius() == 2


def test_font_scale_parsing_and_clamping():
    assert _kde_font("Noto Sans,12,-1,5,50,0,0,0,0,0")[1] == 1.2
    assert _gnome_font("Cantarell 11")[1] == 1.1
    assert _font_scale(6) == 0.85
    assert _font_scale(30) == 1.6
    assert DEFAULT_DARK.font_scale == 1.0
    assert DEFAULT_DARK.has_blur is False
    assert DEFAULT_DARK.corner_radius == 24


def test_kde_without_kwinrc_has_no_blur(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("KDE_FULL_SESSION", "true")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    config = tmp_path / ".config" / "kdeglobals"
    config.parent.mkdir(parents=True)
    config.write_text(
        """
[Colors:Window]
BackgroundNormal=246,245,244
ForegroundNormal=29,29,29
[General]
font=Noto Sans,10,-1,5,50,0,0,0,0,0
""".strip()
    )
    palette = detect_palette()
    assert palette.is_dark is False
    assert palette.has_blur is False
    assert palette.corner_radius == 24


def test_choose_mode(monkeypatch):
    monkeypatch.setattr("atv_remote.pin_display.layer_shell_available", lambda: True)
    base = {"WAYLAND_DISPLAY": "wayland-1", "XDG_SESSION_TYPE": "wayland"}
    assert choose_mode({**base, "XDG_CURRENT_DESKTOP": "KDE"}) == "layer"
    assert choose_mode({**base, "XDG_CURRENT_DESKTOP": "GNOME"}) == "fullscreen"
    assert choose_mode({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}) == "window"

    monkeypatch.setattr("atv_remote.pin_display.layer_shell_available", lambda: False)
    # KDE without layer-shell must not use the full-screen overlay: KWin's
    # blur effects would blur the entire desktop through it.
    assert choose_mode({**base, "XDG_CURRENT_DESKTOP": "KDE"}) == "window"
    assert choose_mode({**base, "XDG_CURRENT_DESKTOP": "GNOME"}) == "fullscreen"




def test_pin_display_disabled():
    display = PinDisplay(enabled=False)
    assert display.available() is False
    assert display.show("1234", 60) is False


def test_qml_files_exist():
    qml = Path(__file__).resolve().parents[1] / "src" / "atv_remote" / "qml"
    assert (qml / "PinCard.qml").is_file()
    assert (qml / "PinWindowLayer.qml").is_file()
    assert (qml / "PinWindowFallback.qml").is_file()
