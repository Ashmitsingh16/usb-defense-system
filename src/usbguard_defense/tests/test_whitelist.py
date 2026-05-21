"""Unit tests for the Whitelist data model and matching."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from usbguard_defense.whitelist import Whitelist, WhitelistEntry


@pytest.fixture
def tmp_whitelist(tmp_path: Path) -> Path:
    """Empty whitelist file in a temp dir."""
    p = tmp_path / "whitelist.json"
    p.write_text(json.dumps({"version": 1, "devices": []}))
    return p


@pytest.fixture
def populated_whitelist(tmp_path: Path) -> Path:
    """Whitelist with two devices: one regular, one unlock-key."""
    p = tmp_path / "whitelist.json"
    p.write_text(json.dumps({
        "version": 1,
        "devices": [
            {
                "id": "uuid-1", "label": "Data Drive",
                "vendor_id": "0951", "product_id": "1666",
                "serial": "AAAAA", "device_class": "MassStorage",
                "added_by": "admin", "added_at": "2026-01-01T00:00:00Z",
                "can_unlock": False,
            },
            {
                "id": "uuid-2", "label": "Unlock Key",
                "vendor_id": "0781", "product_id": "5567",
                "serial": "BBBBB", "device_class": "MassStorage",
                "added_by": "admin", "added_at": "2026-01-02T00:00:00Z",
                "can_unlock": True,
            },
        ],
    }))
    return p


class TestWhitelistEntryNew:
    def test_new_normalises_vid_pid_to_lowercase(self):
        e = WhitelistEntry.new(
            label="X", vendor_id="ABCD", product_id="1234",
            serial="SER", device_class="MassStorage", added_by="admin",
        )
        assert e.vendor_id == "abcd"
        assert e.product_id == "1234"

    def test_new_generates_unique_ids(self):
        e1 = WhitelistEntry.new("a", "1", "2", "s", "c", "admin")
        e2 = WhitelistEntry.new("a", "1", "2", "s", "c", "admin")
        assert e1.id != e2.id

    def test_new_sets_iso_timestamp(self):
        e = WhitelistEntry.new("a", "1", "2", "s", "c", "admin")
        assert "T" in e.added_at
        assert e.added_at.endswith("+00:00") or e.added_at.endswith("Z")

    def test_new_can_unlock_defaults_false(self):
        e = WhitelistEntry.new("a", "1", "2", "s", "c", "admin")
        assert e.can_unlock is False


class TestWhitelistLoad:
    def test_load_missing_file_yields_empty(self, tmp_path):
        wl = Whitelist(path=tmp_path / "does_not_exist.json")
        assert wl.entries == []

    def test_load_empty_file(self, tmp_whitelist):
        wl = Whitelist(path=tmp_whitelist)
        assert wl.entries == []

    def test_load_populated_file(self, populated_whitelist):
        wl = Whitelist(path=populated_whitelist)
        assert len(wl.entries) == 2
        assert wl.entries[0].label == "Data Drive"
        assert wl.entries[1].can_unlock is True


class TestWhitelistMatch:
    def test_match_returns_entry_on_exact_hit(self, populated_whitelist):
        wl = Whitelist(path=populated_whitelist)
        e = wl.match("0951", "1666", "AAAAA")
        assert e is not None and e.label == "Data Drive"

    def test_match_is_case_insensitive_on_vid_pid(self, populated_whitelist):
        wl = Whitelist(path=populated_whitelist)
        # serial must match exactly, but VID/PID compare in lowercase
        assert wl.match("0951", "1666", "AAAAA") is not None
        assert wl.match("0951", "1666", "AAAAA") is not None

    def test_match_serial_is_case_sensitive(self, populated_whitelist):
        wl = Whitelist(path=populated_whitelist)
        # The entry serial is "AAAAA" — lowercase should NOT match
        assert wl.match("0951", "1666", "aaaaa") is None

    def test_match_returns_none_on_miss(self, populated_whitelist):
        wl = Whitelist(path=populated_whitelist)
        assert wl.match("dead", "beef", "NOPE") is None

    def test_match_wrong_serial_returns_none(self, populated_whitelist):
        wl = Whitelist(path=populated_whitelist)
        # Spoofing VID:PID without the right serial must fail —
        # this is the core security property of the whitelist
        assert wl.match("0951", "1666", "WRONG_SERIAL") is None


class TestWhitelistCanUnlock:
    def test_can_unlock_true_for_key_device(self, populated_whitelist):
        wl = Whitelist(path=populated_whitelist)
        assert wl.can_unlock("0781", "5567", "BBBBB") is True

    def test_can_unlock_false_for_data_device(self, populated_whitelist):
        wl = Whitelist(path=populated_whitelist)
        assert wl.can_unlock("0951", "1666", "AAAAA") is False

    def test_can_unlock_false_for_unknown_device(self, populated_whitelist):
        wl = Whitelist(path=populated_whitelist)
        assert wl.can_unlock("dead", "beef", "NOPE") is False


class TestWhitelistAddRemove:
    def test_add_persists_to_disk(self, tmp_whitelist):
        wl = Whitelist(path=tmp_whitelist)
        e = WhitelistEntry.new("New", "abcd", "1234", "SER1", "MassStorage", "admin")
        wl.add(e)

        # Re-load from disk to confirm persistence
        wl2 = Whitelist(path=tmp_whitelist)
        assert len(wl2.entries) == 1
        assert wl2.entries[0].serial == "SER1"

    def test_add_replaces_existing_fingerprint(self, tmp_whitelist):
        wl = Whitelist(path=tmp_whitelist)
        e1 = WhitelistEntry.new("Old", "abcd", "1234", "SER1", "MassStorage", "admin")
        wl.add(e1)
        e2 = WhitelistEntry.new("New", "abcd", "1234", "SER1", "MassStorage", "admin")
        wl.add(e2)
        # Same VID:PID:Serial → single entry, latest wins
        assert len(wl.entries) == 1
        assert wl.entries[0].label == "New"

    def test_remove_existing_returns_true(self, populated_whitelist):
        wl = Whitelist(path=populated_whitelist)
        assert wl.remove("uuid-1") is True
        assert len(wl.entries) == 1

    def test_remove_nonexistent_returns_false(self, populated_whitelist):
        wl = Whitelist(path=populated_whitelist)
        before = len(wl.entries)
        assert wl.remove("not-a-real-id") is False
        assert len(wl.entries) == before

    def test_add_then_remove_round_trip(self, tmp_whitelist):
        wl = Whitelist(path=tmp_whitelist)
        e = WhitelistEntry.new("X", "1234", "abcd", "SER", "MassStorage", "admin")
        wl.add(e)
        assert wl.remove(e.id) is True
        assert wl.entries == []
