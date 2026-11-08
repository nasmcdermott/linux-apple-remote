import os
import shutil

import pytest
from evdev import ecodes

from atv_remote.keymap import DEFAULT_KEYMAP
from atv_remote.output import LogOutput, MprisOutput, UInputOutput, make_output, uinput_status


@pytest.mark.skipif(not os.access("/dev/uinput", os.W_OK), reason="/dev/uinput is not writable")
def test_uinput_backend_creates_device_and_presses_key():
    out = UInputOutput(DEFAULT_KEYMAP)
    try:
        assert out.device_path
        assert out.press("select") is True
        assert out.press("not_an_action") is False
    finally:
        out.close()


def test_log_backend(capsys):
    out = LogOutput()
    assert out.press("up") is True
    assert "[action] up" in capsys.readouterr().out


def test_mpris_backend_maps_media(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    calls = []
    monkeypatch.setattr(
        "atv_remote.output.subprocess.run",
        lambda command, **kwargs: calls.append(command),
    )
    out = MprisOutput()
    assert out.press("play_pause") is True
    assert out.press("volume_up") is True
    assert out.press("mute") is True
    assert out.press("up") is False
    assert calls == [
        ["/usr/bin/playerctl", "play-pause"],
        ["/usr/bin/wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%+"],
        ["/usr/bin/wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"],
    ]


def test_make_output_log():
    assert make_output("log", DEFAULT_KEYMAP).name == "log"


def test_uinput_status_does_not_raise():
    ok, message = uinput_status()
    assert isinstance(ok, bool)
    assert message


@pytest.mark.skipif(not os.access("/dev/uinput", os.W_OK), reason="/dev/uinput is not writable")
def test_uinput_hold_and_release():
    out = UInputOutput(DEFAULT_KEYMAP)
    try:
        assert out.hold("select") is True
        assert out.release("select") is True
        assert out.hold("not_an_action") is False
    finally:
        out.close()


def test_guide_special_action_uses_plasma_dbus(monkeypatch):
    out = UInputOutput(DEFAULT_KEYMAP)
    sent = []
    monkeypatch.setattr("atv_remote.output.is_bigscreen_session", lambda: True)
    monkeypatch.setattr(out, "_plasma_overlay", lambda: True)
    monkeypatch.setattr(out, "_tap_code", lambda code: sent.append(code) or True)
    try:
        assert out.press("guide") is True
        assert sent == []
    finally:
        out.close()


def test_guide_special_action_falls_back_to_key_menu(monkeypatch):
    out = UInputOutput(DEFAULT_KEYMAP)
    sent = []
    monkeypatch.setattr("atv_remote.output.is_bigscreen_session", lambda: False)
    monkeypatch.setattr(out, "_tap_code", lambda code: sent.append(code) or True)
    try:
        assert out.press("guide") is True
        assert sent == [ecodes.KEY_MENU]
    finally:
        out.close()
