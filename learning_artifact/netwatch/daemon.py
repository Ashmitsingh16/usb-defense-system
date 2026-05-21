"""Daemon — the orchestrator.

Reads observations from the sensor queue, updates the baseline, raises alerts
on unknown MACs, drives the responder, and emits structured events. Exposes
a small API (`handle_observation`, `unlock`, `force_freeze`, `add_whitelist`,
`rebuild_baseline`) that both the TUI and CLI use.

Design rule: the daemon NEVER calls platform-specific code directly. All
external effects flow through the injected `Responder` and `Baseline`. Tests
provide fakes for both.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque

from netwatch.auth import verify_at
from netwatch.baseline import Baseline
from netwatch.config import Config
from netwatch.events import Event, EventType, configure_logging, emit
from netwatch.responder import Responder
from netwatch.sensors import Observation, build_sensors
from netwatch.state import Alert, DaemonState, event_for


@dataclass
class UnlockResult:
    ok: bool
    reason: str = ""


class Daemon:
    """Self-contained daemon. Construct with explicit deps for easy testing."""

    # Rate limit — Ashmit's bug #4. Repeated identical alerts within this window
    # for the same MAC are suppressed so an attacker can't DoS via plug/unplug.
    ALERT_DEBOUNCE_SECONDS = 5.0
    MAX_FAILED_UNLOCKS = 5

    def __init__(
        self,
        config: Config,
        *,
        baseline: Baseline | None = None,
        responder: Responder | None = None,
        logger: logging.Logger | None = None,
    ):
        self.config = config
        self.baseline = baseline or Baseline.load(
            config.baseline.path,
            learning_seconds=config.baseline.learning_seconds,
        )
        for mac in config.whitelist:
            try:
                self.baseline.add_whitelist(mac)
            except ValueError:
                continue
        self.responder = responder or Responder()
        self.logger = logger or configure_logging(
            config.logging.dir,
            max_bytes=config.logging.max_bytes,
            backup_count=config.logging.backup_count,
        )
        self.state = DaemonState(baseline=self.baseline)
        self._recent_alerts: Deque[tuple[str, float]] = deque(maxlen=64)
        self._obs_queue: asyncio.Queue[Observation] = asyncio.Queue(maxsize=1024)
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    # =========================================================== lifecycle
    async def run(self) -> None:
        self._emit(EventType.DAEMON_START, "netwatch daemon starting")
        sensors = build_sensors(
            self._obs_queue,
            arp_cache_interval=self.config.sensors.arp_cache_interval,
            arp_scan_interval=self.config.sensors.arp_scan_interval,
            dhcp_enabled=self.config.sensors.dhcp_sniff_enabled,
            iface=self.config.sensors.interface,
        )
        for s in sensors:
            self._tasks.append(s.start())
        self._tasks.append(asyncio.create_task(self._consume(), name="consume"))
        self._tasks.append(asyncio.create_task(self._periodic_save(), name="persist"))

        await self._stop.wait()

        for s in sensors:
            await s.stop()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._emit(EventType.DAEMON_STOP, "netwatch daemon stopped")

    def stop(self) -> None:
        self._stop.set()

    # ============================================================ consume
    async def _consume(self) -> None:
        while not self._stop.is_set():
            try:
                obs = await asyncio.wait_for(self._obs_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                self.handle_observation(obs)
            except Exception as exc:  # pragma: no cover - defensive
                self._emit(EventType.SENSOR_ERROR, f"observation crash: {exc}", source=obs.source)

    async def _periodic_save(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                try:
                    self.baseline.save()
                except OSError:
                    pass

    # ============================================================ handlers
    def handle_observation(self, obs: Observation) -> Alert | None:
        """Process a single observation. Returns the Alert if one was raised."""
        self.state.last_scan = time.time()
        if obs.source.startswith("error:"):
            self._emit(EventType.SENSOR_ERROR, f"sensor error from {obs.source}")
            return None
        try:
            device, is_intruder = self.baseline.observe(
                obs.mac, ip=obs.ip, iface=obs.iface,
            )
        except ValueError:
            return None  # malformed MAC — ignore

        if not is_intruder:
            return None

        # Debounce: same MAC within window -> swallow.
        now = time.monotonic()
        for mac, ts in self._recent_alerts:
            if mac == device.mac and (now - ts) < self.ALERT_DEBOUNCE_SECONDS:
                return None
        self._recent_alerts.append((device.mac, now))

        alert = self.state.record_alert(obs, vendor=device.vendor)
        self._emit(
            EventType.INTRUDER,
            f"intruder {device.mac} ({device.vendor}) via {obs.source}",
            mac=device.mac,
            ip=obs.ip,
            vendor=device.vendor,
            iface=obs.iface,
            source=obs.source,
        )
        self._trigger_response(alert)
        return alert

    def _trigger_response(self, alert: Alert) -> None:
        if self.state.locked:
            return  # already in lockdown — don't re-fire
        if self.config.responder.freeze_network:
            outcome = self.responder.freeze(
                fallback_iface=alert.iface if self.config.responder.fallback_iface_down else None,
            )
            self.state.frozen = outcome.success
            self._emit(
                EventType.FREEZE,
                outcome.summary(),
                method=outcome.method,
                success=outcome.success,
                preserved_ssh=outcome.preserved_ssh,
            )
        self.state.mark_locked(alert)
        self._emit(EventType.LOCK, f"system locked; reason {alert.mac}")

    # ============================================================ controls
    def unlock(self, password: str) -> UnlockResult:
        if not self.state.locked:
            return UnlockResult(ok=False, reason="not locked")
        if self.state.failed_unlocks >= self.MAX_FAILED_UNLOCKS:
            return UnlockResult(ok=False, reason="too many failed attempts; restart daemon")
        if not verify_at(self.config.auth_path, password):
            self.state.failed_unlocks += 1
            self._emit(EventType.UNLOCK_FAIL, "unlock attempt failed", attempt=self.state.failed_unlocks)
            return UnlockResult(ok=False, reason="bad password")
        outcome = self.responder.unfreeze()
        self.state.frozen = False
        self.state.mark_unlocked()
        self._emit(EventType.UNFREEZE, outcome.summary())
        self._emit(EventType.UNLOCK, "system unlocked by operator")
        return UnlockResult(ok=True)

    def force_freeze(self) -> None:
        synthetic = Alert(
            timestamp=time.time(), mac="manual", ip=None,
            vendor="operator", iface=None, source="manual",
        )
        self._trigger_response(synthetic)

    def add_whitelist(self, mac: str) -> bool:
        try:
            self.baseline.add_whitelist(mac)
        except ValueError:
            return False
        self._emit(EventType.WHITELIST_ADD, f"whitelisted {mac}", mac=mac)
        return True

    def remove_whitelist(self, mac: str) -> bool:
        try:
            removed = self.baseline.remove_whitelist(mac)
        except ValueError:
            return False
        if removed:
            self._emit(EventType.WHITELIST_REMOVE, f"un-whitelisted {mac}", mac=mac)
        return removed

    def rebuild_baseline(self) -> None:
        self.baseline.reset_learning()
        self._emit(EventType.BASELINE_REBUILD, "baseline cleared; learning restarted")

    # =============================================================== utils
    def _emit(self, event_type: EventType, message: str, **data: object) -> Event:
        ev = event_for(event_type, message, **data)
        self.state.push_event(ev)
        emit(self.logger, ev)
        return ev
