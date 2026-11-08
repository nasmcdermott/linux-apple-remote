from __future__ import annotations

from atv_remote.cli import _replace_kwin_corner_radius


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
