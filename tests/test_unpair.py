from __future__ import annotations

from atv_remote import cli
from atv_remote.config import config_text
from atv_remote.server import Identity


def make_state(tmp_path, *clients):
    config = tmp_path / "config.toml"
    config.write_text(config_text())
    identity = Identity(tmp_path / "state.json")
    identity.clients = {client: "00" * 32 for client in clients}
    identity.save()
    return config


def test_unpair_list_and_all(tmp_path, monkeypatch, capsys):
    config = make_state(tmp_path, "AAAA1111", "BBBB2222")
    monkeypatch.setattr(cli, "_run", lambda argv: (0, "inactive"))

    assert cli.main(["--config", str(config), "unpair", "--list"]) == 0
    out = capsys.readouterr().out
    assert "AAAA1111" in out and "BBBB2222" in out

    assert cli.main(["--config", str(config), "unpair", "--all", "--no-service"]) == 0
    assert Identity(tmp_path / "state.json").clients == {}
    assert "Removed 2" in capsys.readouterr().out


def test_unpair_one_by_prefix(tmp_path, monkeypatch, capsys):
    config = make_state(tmp_path, "AAAA1111", "BBBB2222")
    monkeypatch.setattr(cli, "_run", lambda argv: (0, "inactive"))

    assert cli.main(["--config", str(config), "unpair", "--client", "AAAA", "--no-service"]) == 0
    assert Identity(tmp_path / "state.json").clients == {"BBBB2222": "00" * 32}
    assert "Removed 1" in capsys.readouterr().out


def test_unpair_no_devices(tmp_path, monkeypatch, capsys):
    config = make_state(tmp_path)
    monkeypatch.setattr(cli, "_run", lambda argv: (0, "inactive"))
    assert cli.main(["--config", str(config), "unpair", "--all", "--no-service"]) == 0
    assert "No paired devices" in capsys.readouterr().out
