import os
import time

import pytest

from atv_remote.cec import CecConfig
from atv_remote.config import Config, config_text, load_config, write_default_config
from atv_remote.keymap import (
    DEFAULT_KEYMAP,
    SPECIAL_KEYS,
    code_for,
    resolve_key_name,
    validate_keymap,
)
from atv_remote.pairing import PairingGate


def test_default_config_roundtrip(tmp_path):
    path = tmp_path / "config.toml"
    write_default_config(path, name="Living Room", port=50000, backend="log")
    cfg = load_config(path)
    assert cfg.name == "Living Room"
    assert cfg.port == 50000
    assert cfg.backend == "log"
    assert cfg.keymap["select"] == "KEY_ENTER"


def test_unknown_action_is_ignored_and_unknown_key_is_rejected():
    assert validate_keymap({"up": "KEY_UP", "not_an_action": "KEY_ENTER"}) == {"up": "KEY_UP"}
    with pytest.raises(ValueError):
        validate_keymap({"up": "KEY_NOT_REAL"})


def test_all_default_keys_resolve():
    for action, key in DEFAULT_KEYMAP.items():
        resolved = resolve_key_name(action, key)
        if resolved in SPECIAL_KEYS:
            continue
        assert code_for(resolved) > 0, action


def test_guide_uses_bigscreen_overlay_action():
    assert DEFAULT_KEYMAP["guide"] == "bigscreen_overlay"
    assert resolve_key_name("guide", "bigscreen_overlay") == "bigscreen_overlay"
    assert validate_keymap({"guide": "bigscreen_overlay"}) == {"guide": "bigscreen_overlay"}


def test_home_auto_uses_bigscreen_shortcut(monkeypatch):
    monkeypatch.setenv("DESKTOP_SESSION", "plasma-bigscreen-wayland")
    assert resolve_key_name("home", "auto") == "KEY_HOMEPAGE"
    monkeypatch.setenv("DESKTOP_SESSION", "plasma")
    assert resolve_key_name("home", "auto") == "KEY_LEFTMETA"


def test_auto_is_only_for_home():
    assert validate_keymap({"home": "auto"}) == {"home": "auto"}
    with pytest.raises(ValueError):
        validate_keymap({"up": "auto"})


def test_config_rejects_bad_backend(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(config_text(backend="uinput").replace('"uinput"', '"nope"'))
    with pytest.raises(ValueError):
        load_config(path)


def test_pairing_gate(tmp_path):
    gate = PairingGate(tmp_path / "pairing", window_seconds=60)
    assert not gate.allowed()
    gate.touch()
    assert gate.allowed()
    assert gate.age() is not None
    gate.close()
    assert not gate.allowed()


def test_pairing_gate_expires(tmp_path):
    gate = PairingGate(tmp_path / "pairing", window_seconds=1)
    gate.touch()
    os.utime(gate.path, (time.time() - 2, time.time() - 2))
    assert not gate.allowed()


def test_pairing_gate_zero_disables(tmp_path):
    gate = PairingGate(tmp_path / "pairing", window_seconds=0)
    gate.touch()
    assert not gate.allowed()


def test_config_defaults_are_valid():
    Config().validate()


def test_config_text_includes_cec_and_new_keys():
    text = config_text()
    assert "[cec]" in text
    assert 'power = "KEY_POWER"' in text
    assert 'channel_up = "KEY_CHANNELUP"' in text
    # PIN display moved to a GUI-only card; there is no notification setting.
    assert "notify" not in text
    assert 'pin_display = "auto"' in text


def test_pin_display_roundtrip(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(config_text(pin_display="none"))
    cfg = load_config(path)
    assert cfg.pin_display == "none"


def test_pin_display_rejects_unknown_value(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(config_text(pin_display="nope"))
    with pytest.raises(ValueError):
        load_config(path)


def test_cec_config_roundtrip(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        config_text(
            cec=CecConfig(enabled=False, policy="/tmp/policy", volume=False, power_on=False)
        )
    )
    cfg = load_config(path)
    assert cfg.cec.enabled is False
    assert cfg.cec.policy == "/tmp/policy"
    assert cfg.cec.volume is False
    assert cfg.cec.power_on is False
