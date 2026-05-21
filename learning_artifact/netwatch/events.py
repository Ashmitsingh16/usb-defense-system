"""Event model and structured logging setup.

Events are the daemon's one canonical record of what happened. They flow:
  daemon -> structlog -> RotatingFileHandler (JSONL) + optional journald
and also onto an asyncio.Queue consumed by the TUI for live tailing.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class EventType(str, Enum):
    DEVICE_SEEN = "device_seen"
    DEVICE_NEW = "device_new"
    INTRUDER = "intruder"
    FREEZE = "freeze"
    UNFREEZE = "unfreeze"
    LOCK = "lock"
    UNLOCK = "unlock"
    UNLOCK_FAIL = "unlock_fail"
    SENSOR_ERROR = "sensor_error"
    DAEMON_START = "daemon_start"
    DAEMON_STOP = "daemon_stop"
    BASELINE_REBUILD = "baseline_rebuild"
    WHITELIST_ADD = "whitelist_add"
    WHITELIST_REMOVE = "whitelist_remove"


@dataclass
class Event:
    type: EventType
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, Event):
            return record.msg.to_json()
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        return json.dumps(payload, default=str)


def configure_logging(log_dir: Path, *, max_bytes: int, backup_count: int) -> logging.Logger:
    """Configure the root 'netwatch' logger with rotating JSONL output."""
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("netwatch")
    logger.setLevel(logging.INFO)
    # Idempotent: clear handlers on reconfigure (matters for tests).
    for h in list(logger.handlers):
        logger.removeHandler(h)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "events.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(_JSONFormatter())
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def emit(logger: logging.Logger, event: Event) -> None:
    """Log an Event as a structured record."""
    logger.info(event)
