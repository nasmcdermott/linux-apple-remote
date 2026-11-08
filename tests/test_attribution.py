"""Keep upstream names and license text from silently disappearing."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_upstream_authors_are_named() -> None:
    notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
    credits = (ROOT / "docs" / "CREDITS.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for name in (
        "Arya Kavian",
        "windows-apple-remote",
        "vb3",
        "atvr4samsung",
        "Pierre Ståhl",
        "pyatv",
    ):
        assert name in notice, name
        assert name in credits, name

    assert "Arya Kavian" in readme
    assert "vb3" in readme


def test_upstream_mit_text_is_present() -> None:
    license_file = ROOT / "LICENSES" / "windows-apple-remote-MIT.txt"
    assert license_file.is_file()
    text = license_file.read_text(encoding="utf-8")
    assert "MIT License" in text
    assert "Arya Kavian" in text
