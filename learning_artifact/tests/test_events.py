from __future__ import annotations

import json
import logging
from pathlib import Path

from netwatch.events import Event, EventType, configure_logging, emit


def test_event_to_json_roundtrip() -> None:
    e = Event(type=EventType.INTRUDER, message="hi", data={"mac": "aa:bb:cc:dd:ee:01"})
    blob = e.to_json()
    parsed = json.loads(blob)
    assert parsed["type"] == "intruder"
    assert parsed["data"]["mac"] == "aa:bb:cc:dd:ee:01"


def test_configure_logging_writes_jsonl(tmp_path: Path) -> None:
    logger = configure_logging(tmp_path / "logs", max_bytes=1024, backup_count=2)
    emit(logger, Event(type=EventType.DAEMON_START, message="up"))
    # flush
    for h in logger.handlers:
        h.flush()
    log_file = tmp_path / "logs" / "events.log"
    assert log_file.exists()
    lines = log_file.read_text().splitlines()
    assert lines, "expected at least one event line"
    parsed = json.loads(lines[0])
    assert parsed["type"] == "daemon_start"


def test_configure_logging_handles_plain_records(tmp_path: Path) -> None:
    logger = configure_logging(tmp_path / "logs", max_bytes=1024, backup_count=1)
    logger.info("hello world")
    for h in logger.handlers:
        h.flush()
    blob = (tmp_path / "logs" / "events.log").read_text().strip()
    parsed = json.loads(blob.splitlines()[-1])
    assert parsed["message"] == "hello world"
    assert parsed["level"] == "INFO"


def test_configure_logging_idempotent(tmp_path: Path) -> None:
    logger = configure_logging(tmp_path / "logs", max_bytes=1024, backup_count=1)
    n = len(logger.handlers)
    logger = configure_logging(tmp_path / "logs", max_bytes=1024, backup_count=1)
    assert len(logger.handlers) == n
