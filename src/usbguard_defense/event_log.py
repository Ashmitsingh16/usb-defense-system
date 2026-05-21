"""Append-only event log writer (in addition to journald)."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import EVENT_LOG_PATH


log = logging.getLogger(__name__)


class EventLogger:
    """Writes one JSON line per event to a flat file. Thread-safe."""

    def __init__(self, path: Path = EVENT_LOG_PATH):
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event_type: str, event: dict) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            **event,
        }
        line = json.dumps(record, default=str) + "\n"
        with self._lock:
            try:
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
                    fh.flush()
                    os.fsync(fh.fileno())
            except OSError:
                log.exception("Failed to write event log")

    def read_recent(self, limit: int = 200) -> list[dict]:
        if not self.path.exists():
            return []
        with self._lock:
            try:
                with self.path.open("r", encoding="utf-8") as fh:
                    lines = fh.readlines()
            except OSError:
                return []
        out: list[dict] = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
