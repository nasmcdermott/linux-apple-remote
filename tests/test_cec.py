from __future__ import annotations

import os
import time

from atv_remote.cec import CecConfig, CecOutput, CecPolicy, find_policy


class FakeInner:
    name = "fake"
    device_path = "/dev/null"

    def __init__(self) -> None:
        self.actions: list[str] = []
        self.closed = False

    def press(self, action: str) -> bool:
        self.actions.append(action)
        return True

    def close(self) -> None:
        self.closed = True


class FakePolicy:
    def __init__(self) -> None:
        self.volumes: list[str] = []
        self.wakes = 0
        self.closed = False

    def volume(self, direction: str) -> bool:
        self.volumes.append(direction)
        return True

    def wake(self) -> bool:
        self.wakes += 1
        return True

    def close(self) -> None:
        self.closed = True


def make() -> tuple[FakeInner, FakePolicy, CecOutput]:
    inner = FakeInner()
    policy = FakePolicy()
    return inner, policy, CecOutput(inner, policy, CecConfig())


def test_volume_and_mute_go_to_cec():
    inner, policy, output = make()
    assert output.press("volume_up")
    assert output.press("volume_down")
    assert output.press("mute")
    assert policy.volumes == ["up", "down", "mute"]
    assert inner.actions == []


def test_power_emits_key_and_wakes_tv():
    inner, policy, output = make()
    assert output.press("power")
    assert inner.actions == ["power"]
    assert policy.wakes == 1


def test_power_on_can_be_disabled():
    inner = FakeInner()
    policy = FakePolicy()
    output = CecOutput(inner, policy, CecConfig(power_on=False))
    output.press("power")
    assert inner.actions == ["power"]
    assert policy.wakes == 0


def test_volume_flag_falls_back_to_inner_keys():
    inner = FakeInner()
    policy = FakePolicy()
    output = CecOutput(inner, policy, CecConfig(volume=False))
    output.press("volume_up")
    assert inner.actions == ["volume_up"]
    assert policy.volumes == []


def test_other_actions_pass_through():
    inner, _, output = make()
    output.press("channel_up")
    output.press("guide")
    assert inner.actions == ["channel_up", "guide"]


def test_close_closes_both():
    inner, policy, output = make()
    output.close()
    assert inner.closed and policy.closed


def test_find_policy_explicit(tmp_path):
    script = tmp_path / "cec-policy"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)
    assert find_policy(str(script)) == str(script)
    script.chmod(0o644)
    assert find_policy(str(script)) is None


def test_find_policy_missing_returns_none(tmp_path):
    assert find_policy(str(tmp_path / "nope")) is None


def test_wake_is_debounced(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "atv_remote.cec.subprocess.Popen", lambda *args, **kwargs: calls.append(args)
    )
    policy = CecPolicy("/bin/true", timeout=2)
    try:
        assert policy.wake() is True
        assert policy.wake() is False
    finally:
        policy.close()
    assert len(calls) == 1


def test_policy_worker_accepts_volume(tmp_path):
    script = tmp_path / "cec-policy"
    log = tmp_path / "calls"
    script.write_text(f'#!/bin/sh\necho "$@" >> {log}\n')
    script.chmod(0o755)
    policy = CecPolicy(str(script), timeout=5)
    try:
        assert policy.volume("up")
        deadline = time.monotonic() + 3
        while not log.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        policy.close()
    assert "volume up" in log.read_text()
    assert os.access(script, os.X_OK)
