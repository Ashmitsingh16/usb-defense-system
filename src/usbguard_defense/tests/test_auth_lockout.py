"""Tests for the daemon's unlock-attempt rate limiter (v0.3.0).

We bypass `Daemon.__init__` (it touches udev, USBGuard, sd_notify and a
master-key file) and just rebuild the state the lockout uses. The
methods under test only touch self-attributes plus self.event_log, so
this is enough to lock the policy down.

Policy summary:
- First 4 failures: silent (next attempt still allowed).
- 5th failure (== AUTH_FAILURE_THRESHOLD): lockout for
  AUTH_LOCKOUT_SECONDS.
- Each subsequent failure doubles the wait (60 → 120 → 240 → …).
- A successful auth clears both the counter and the lockout window.
"""

from __future__ import annotations

import sys
import threading
from types import ModuleType, SimpleNamespace

# pyudev is a Linux-only C extension that monitor.py imports at module
# load. The daemon module pulls monitor in transitively, so we stub
# pyudev before the import on hosts where it isn't installed (Windows
# CI / local dev).
if "pyudev" not in sys.modules:
    sys.modules["pyudev"] = ModuleType("pyudev")

from usbguard_defense.daemon import Daemon  # noqa: E402


def _make_daemon():
    d = Daemon.__new__(Daemon)
    d._auth_failures = 0
    d._auth_lockout_until = 0.0
    d._auth_lock = threading.Lock()
    d.event_log = SimpleNamespace(write=lambda *_a, **_kw: None)
    return d


def test_initially_not_locked_out():
    d = _make_daemon()
    assert d._auth_locked_out() == 0.0


def test_four_failures_does_not_lock_out():
    d = _make_daemon()
    for _ in range(Daemon.AUTH_FAILURE_THRESHOLD - 1):
        d._record_auth_failure("unlock_with_password")
    assert d._auth_locked_out() == 0.0


def test_fifth_failure_engages_lockout():
    d = _make_daemon()
    for _ in range(Daemon.AUTH_FAILURE_THRESHOLD):
        d._record_auth_failure("unlock_with_password")
    remaining = d._auth_locked_out()
    assert 0 < remaining <= Daemon.AUTH_LOCKOUT_SECONDS


def test_lockout_doubles_each_extra_failure():
    d = _make_daemon()
    base = Daemon.AUTH_LOCKOUT_SECONDS
    # Threshold reached → base seconds.
    for _ in range(Daemon.AUTH_FAILURE_THRESHOLD):
        d._record_auth_failure("op")
    first = d._auth_locked_out()
    assert first <= base
    # +1 more → 2x.
    d._record_auth_failure("op")
    second = d._auth_locked_out()
    assert base < second <= base * 2
    # +1 more → 4x.
    d._record_auth_failure("op")
    third = d._auth_locked_out()
    assert base * 2 < third <= base * 4


def test_success_clears_counter_and_lockout():
    d = _make_daemon()
    for _ in range(Daemon.AUTH_FAILURE_THRESHOLD + 2):
        d._record_auth_failure("op")
    assert d._auth_locked_out() > 0
    d._record_auth_success()
    assert d._auth_locked_out() == 0.0
    assert d._auth_failures == 0


def test_lockout_records_an_event():
    d = _make_daemon()
    written: list[tuple[str, dict]] = []
    d.event_log = SimpleNamespace(write=lambda kind, payload: written.append((kind, payload)))
    for _ in range(Daemon.AUTH_FAILURE_THRESHOLD):
        d._record_auth_failure("simulate_event")
    assert any(
        kind == "AUTH_LOCKOUT" and payload["op"] == "simulate_event"
        for kind, payload in written
    )
