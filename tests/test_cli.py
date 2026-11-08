from __future__ import annotations

import asyncio

from atv_remote.cli import _replace_kwin_corner_radius, _virtual_iface, _wait_for_lan_ip


def test_virtual_interface_detection():
    assert _virtual_iface("docker0")
    assert _virtual_iface("veth123")
    assert _virtual_iface("virbr0")
    assert _virtual_iface("lo")
    assert not _virtual_iface("wlp16s0")
    assert not _virtual_iface("enp4s0")


def test_wait_for_lan_ip_skips_container_bridge(monkeypatch):
    values = iter(["172.17.0.1", "192.168.1.5"])
    monkeypatch.setattr("atv_remote.cli.local_ip", lambda: next(values))
    monkeypatch.setattr(
        "atv_remote.cli._ip_is_virtual", lambda address: address == "172.17.0.1"
    )
    assert asyncio.run(_wait_for_lan_ip(1)) == "192.168.1.5"


def test_replace_kwin_corner_radius_preserves_other_settings(tmp_path):
    path = tmp_path / "kwinrc"
    path.write_text(
        "[Effect-better-blur-dx]\n"
        "CornerRadius=2\n"
        "RefractionEdgeSize=25\n"
        "[Other]\n"
        "Keep=1\n",
        encoding="utf-8",
    )

    assert _replace_kwin_corner_radius(path, "Effect-better-blur-dx", 28) is True

    text = path.read_text(encoding="utf-8")
    assert "CornerRadius=28" in text
    assert "RefractionEdgeSize=25" in text
    assert "[Other]\nKeep=1" in text


def test_replace_kwin_corner_radius_adds_missing_section(tmp_path):
    path = tmp_path / "kwinrc"
    path.write_text("[Plugins]\nbetter_blur_dxEnabled=true\n", encoding="utf-8")

    assert _replace_kwin_corner_radius(path, "Effect-better-blur-dx", 28) is True

    text = path.read_text(encoding="utf-8")
    assert "[Effect-better-blur-dx]\nCornerRadius=28" in text
