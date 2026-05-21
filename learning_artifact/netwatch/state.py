"""Shared daemon state — the bridge between sensors, responder, TUI, and CLI.

Kept deliberately small and immutable-ish so a future IPC layer can serialize
it without touching business logic.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

from netwatch.baseline import Baseline
from netwatch.events import Event, EventType
from netwatch.sensors import Observation


@dataclass
class Alert:
    timestamp: float
    mac: str
    ip: str | None
    vendor: str
    iface: str | None
    source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "mac": self.mac,
            "ip": self.ip,
            "vendor": self.vendor,
            "iface": self.iface,
            "source": self.source,
        }


@dataclass
class DaemonState:
    baseline: Baseline
    locked: bool = False
    lock_reason: Alert | None = None
    frozen: bool = False
    started_at: float = field(default_factory=time.monotonic)
    last_scan: float = 0.0
    alerts: Deque[Alert] = field(default_factory=lambda: deque(maxlen=200))
    events: Deque[Event] = field(default_factory=lambda: deque(maxlen=500))
    event_queue: "asyncio.Queue[Event]" = field(default_factory=asyncio.Queue)
    failed_unlocks: int = 0

    # ------------------------------------------------------------- mutators
    def push_event(self, event: Event) -> None:
        self.events.append(event)
        # Non-blocking: drop oldest if TUI isn't draining (use a generous queue).
        try:
            self.event_queue.put_nowait(event)
        except asyncio.QueueFull:  # pragma: no cover - default queue is unbounded
            pass

    def record_alert(self, obs: Observation, vendor: str) -> Alert:
        alert = Alert(
            timestamp=time.time(),
            mac=obs.mac,
            ip=obs.ip,
            vendor=vendor,
            iface=obs.iface,
            source=obs.source,
        )
        self.alerts.append(alert)
        return alert

    def mark_locked(self, alert: Alert) -> None:
        self.locked = True
        self.lock_reason = alert

    def mark_unlocked(self) -> None:
        self.locked = False
        self.lock_reason = None
        self.failed_unlocks = 0

    def status_dict(self) -> dict[str, object]:
        return {
            "locked": self.locked,
            "frozen": self.frozen,
            "uptime_seconds": round(time.monotonic() - self.started_at, 1),
            "last_scan": self.last_scan,
            "baseline_size": len(self.baseline.devices),
            "whitelist_size": len(self.baseline.whitelist),
            "learning": self.baseline.is_learning(),
            "alerts": len(self.alerts),
            "failed_unlocks": self.failed_unlocks,
            "lock_reason": self.lock_reason.to_dict() if self.lock_reason else None,
        }


# Convenience: build an Event for a standard transition.
def event_for(event_type: EventType, message: str, **data: object) -> Event:
    return Event(type=event_type, message=message, data=dict(data))
