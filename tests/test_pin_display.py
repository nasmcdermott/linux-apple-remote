from __future__ import annotations

from pathlib import Path

from atv_remote.palette import detect_palette, is_dark_color, parse_color
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
[Colors:Selection]
BackgroundNormal=74,144,217
[General]
font=SF Pro Text,10,-1,5,50,0,0,0,0,0
""".strip()
    )
    palette = detect_palette()
    assert palette.background == "#111111"
    assert palette.foreground == "#ffffff"
    assert palette.accent == "#4a90d9"
    assert palette.font_family == "SF Pro Text"
    assert palette.is_dark is True


def test_choose_mode(monkeypatch):
    monkeypatch.setattr("atv_remote.pin_display.layer_shell_available", lambda: True)
    base = {"WAYLAND_DISPLAY": "wayland-1", "XDG_SESSION_TYPE": "wayland"}
    assert choose_mode({**base, "XDG_CURRENT_DESKTOP": "KDE"}) == "layer"
    assert choose_mode({**base, "XDG_CURRENT_DESKTOP": "GNOME"}) == "fullscreen"
    assert choose_mode({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}) == "window"


def test_pin_display_disabled():
    display = PinDisplay(enabled=False)
    assert display.available() is False
    assert display.show("1234", 60) is False


def test_qml_files_exist():
    qml = Path(__file__).resolve().parents[1] / "src" / "atv_remote" / "qml"
    assert (qml / "PinCard.qml").is_file()
    assert (qml / "PinWindowLayer.qml").is_file()
    assert (qml / "PinWindowFallback.qml").is_file()
