"""Unit tests for the append-only event logger."""

from __future__ import annotations

import json
from pathlib import Path

from usbguard_defense.event_log import EventLogger


def test_write_creates_file(tmp_path: Path):
    log_path = tmp_path / "events.log"
    el = EventLogger(path=log_path)
    el.write("AUTHORIZED", {"vendor_id": "0951"})
    assert log_path.exists()


def test_each_write_produces_one_json_line(tmp_path: Path):
    log_path = tmp_path / "events.log"
    el = EventLogger(path=log_path)
    el.write("AUTHORIZED", {"vendor_id": "0951"})
    el.write("UNAUTHORIZED", {"vendor_id": "dead"})
    el.write("REMOVE", {"vendor_id": "0951"})
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        record = json.loads(line)
        assert "ts" in record
        assert "type" in record


def test_write_includes_iso_timestamp(tmp_path: Path):
    el = EventLogger(path=tmp_path / "events.log")
    el.write("AUTHORIZED", {"vendor_id": "0951"})
    record = json.loads((tmp_path / "events.log").read_text().strip())
    assert "T" in record["ts"]  # ISO 8601 has T between date and time


def test_event_type_recorded_as_type_field(tmp_path: Path):
    el = EventLogger(path=tmp_path / "events.log")
    el.write("UNAUTHORIZED", {"vendor_id": "dead"})
    record = json.loads((tmp_path / "events.log").read_text().strip())
    assert record["type"] == "UNAUTHORIZED"


def test_extra_fields_merged_into_record(tmp_path: Path):
    el = EventLogger(path=tmp_path / "events.log")
    el.write("AUTHORIZED", {
        "vendor_id": "0951",
        "product_id": "1666",
        "serial": "ABCD",
        "label": "My Drive",
    })
    record = json.loads((tmp_path / "events.log").read_text().strip())
    assert record["vendor_id"] == "0951"
    assert record["product_id"] == "1666"
    assert record["serial"] == "ABCD"
    assert record["label"] == "My Drive"


def test_read_recent_returns_most_recent(tmp_path: Path):
    el = EventLogger(path=tmp_path / "events.log")
    for i in range(5):
        el.write("AUTHORIZED", {"i": i})
    recent = el.read_recent(limit=3)
    assert len(recent) == 3
    assert [r["i"] for r in recent] == [2, 3, 4]


def test_read_recent_empty_when_no_file(tmp_path: Path):
    el = EventLogger(path=tmp_path / "events.log")
    # Don't write anything — file was created during __init__'s parent.mkdir
    # but the log file itself doesn't exist until first write
    assert el.read_recent() == []


def test_read_recent_skips_malformed_lines(tmp_path: Path):
    log_path = tmp_path / "events.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        '{"ts":"2026-01-01","type":"OK"}\n'
        'this is not json\n'
        '{"ts":"2026-01-02","type":"OK2"}\n'
    )
    el = EventLogger(path=log_path)
    recent = el.read_recent()
    assert len(recent) == 2
    assert recent[0]["type"] == "OK"
    assert recent[1]["type"] == "OK2"
