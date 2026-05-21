from __future__ import annotations

from pathlib import Path

from netwatch import oui


def test_known_vendor() -> None:
    assert oui.lookup("b8:27:eb:11:22:33") == "Raspberry Pi Foundation"


def test_unknown_vendor() -> None:
    assert oui.lookup("ff:ff:ff:00:00:00") == "Unknown"


def test_short_mac_unknown() -> None:
    assert oui.lookup("ab:cd") == "Unknown"


def test_extra_overrides(tmp_path: Path) -> None:
    p = tmp_path / "manuf"
    p.write_text("01:23:45  CustomCo  # comment\n# full-line comment\nbadline\n")
    extra = oui.load_extra(p)
    assert extra["012345"] == "CustomCo"
    assert oui.lookup("01:23:45:99:99:99", extra=extra) == "CustomCo"


def test_load_extra_missing(tmp_path: Path) -> None:
    assert oui.load_extra(tmp_path / "no.txt") == {}
