from __future__ import annotations

from types import SimpleNamespace

from atv_remote.notify import available, notify


def test_unavailable_without_notify_send(monkeypatch):
    monkeypatch.setattr("atv_remote.notify.shutil.which", lambda _: None)
    assert available() is False
    assert notify("hello") is False


def test_notify_builds_command(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("atv_remote.notify.shutil.which", lambda _: "/usr/bin/notify-send")
    monkeypatch.setattr("atv_remote.notify.subprocess.run", fake_run)

    assert available() is True
    assert notify("Apple TV Remote", "PIN 1234", timeout_ms=5000) is True
    assert calls == [
        [
            "/usr/bin/notify-send",
            "-a",
            "Apple TV Remote",
            "-t",
            "5000",
            "Apple TV Remote",
            "PIN 1234",
        ]
    ]
