from __future__ import annotations

import time
from pathlib import Path

import pytest

from netwatch.baseline import Baseline, Device, normalize_mac


def test_normalize_mac_variants() -> None:
    assert normalize_mac("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"
    assert normalize_mac("AABBCCDDEEFF") == "aa:bb:cc:dd:ee:ff"
    assert normalize_mac("aa:b:cc:d:ee:f") == "aa:0b:cc:0d:ee:0f"


def test_normalize_mac_invalid() -> None:
    with pytest.raises(ValueError):
        normalize_mac("nope")


def test_learning_period(tmp_path: Path) -> None:
    b = Baseline(path=tmp_path / "bl.json", learning_seconds=10)
    dev, is_intruder = b.observe("aa:bb:cc:dd:ee:01", ip="10.0.0.1")
    assert isinstance(dev, Device)
    assert is_intruder is False
    assert b.is_learning() is True
    assert b.is_known("aa:bb:cc:dd:ee:01")


def test_alert_after_learning(tmp_path: Path) -> None:
    b = Baseline(path=tmp_path / "bl.json", learning_seconds=0)
    _, first = b.observe("aa:bb:cc:dd:ee:01")
    assert first is True  # learning over -> new MAC = intruder
    _, again = b.observe("aa:bb:cc:dd:ee:01")
    assert again is False  # already known


def test_whitelist_suppresses_alert(tmp_path: Path) -> None:
    b = Baseline(path=tmp_path / "bl.json", learning_seconds=0)
    b.add_whitelist("AA:BB:CC:DD:EE:01")
    _, is_intruder = b.observe("aa:bb:cc:dd:ee:01")
    assert is_intruder is False


def test_remove_whitelist(tmp_path: Path) -> None:
    b = Baseline(path=tmp_path / "bl.json", learning_seconds=0)
    b.add_whitelist("aa:bb:cc:dd:ee:01")
    assert b.remove_whitelist("aa:bb:cc:dd:ee:01") is True
    assert b.remove_whitelist("aa:bb:cc:dd:ee:01") is False


def test_save_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "bl.json"
    b = Baseline(path=p, learning_seconds=0)
    b.observe("aa:bb:cc:dd:ee:01", ip="10.0.0.1")
    b.add_whitelist("aa:bb:cc:dd:ee:02")
    b.save()

    b2 = Baseline.load(p, learning_seconds=999)
    assert b2.is_known("aa:bb:cc:dd:ee:01")
    assert "aa:bb:cc:dd:ee:02" in b2.whitelist
    # Loaded baseline should NOT be in learning mode
    assert b2.is_learning() is False


def test_load_missing_returns_fresh(tmp_path: Path) -> None:
    b = Baseline.load(tmp_path / "nope.json")
    assert len(b.devices) == 0


def test_load_corrupt_file(tmp_path: Path) -> None:
    p = tmp_path / "bl.json"
    p.write_text("not json {{{")
    b = Baseline.load(p)
    assert len(b.devices) == 0


def test_reset_learning_clears(tmp_path: Path) -> None:
    b = Baseline(path=tmp_path / "bl.json", learning_seconds=10)
    b.observe("aa:bb:cc:dd:ee:01")
    b.reset_learning()
    assert len(b.devices) == 0
    assert b.is_learning() is True


def test_observe_updates_existing(tmp_path: Path) -> None:
    b = Baseline(path=tmp_path / "bl.json", learning_seconds=10)
    b.observe("aa:bb:cc:dd:ee:01", ip="10.0.0.1")
    dev, _ = b.observe("aa:bb:cc:dd:ee:01", ip="10.0.0.2", hostname="host", iface="eth0")
    assert dev.last_ip == "10.0.0.2"
    assert dev.hostname == "host"
    assert dev.iface == "eth0"
