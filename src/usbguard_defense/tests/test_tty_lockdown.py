"""Tests for the TTY lockdown helper.

``tty_lockdown`` shells out to ``systemctl mask`` / ``unmask`` and
writes a drop-in under ``/run/systemd/logind.conf.d/`` — neither exists
on Windows. We patch ``subprocess.run`` and the drop-in path so the
module's contract is verified without needing a Linux host.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from usbguard_defense import tty_lockdown


@pytest.fixture(autouse=True)
def _isolate_logind_dropin(tmp_path, monkeypatch):
    dropin_dir = tmp_path / "logind.conf.d"
    monkeypatch.setattr(tty_lockdown, "_LOGIND_RUNTIME_DROPIN_DIR", dropin_dir)
    monkeypatch.setattr(
        tty_lockdown, "_LOGIND_RUNTIME_DROPIN",
        dropin_dir / "50-usbdefense-lock.conf",
    )
    yield


def _systemctl_calls(run_mock) -> list[list[str]]:
    return [
        call.args[0] for call in run_mock.call_args_list
        if call.args and isinstance(call.args[0], list)
        and call.args[0][0] == "systemctl"
    ]


def test_lock_tty_covers_getty_and_autovt_for_tty1_through_6() -> None:
    with patch.object(tty_lockdown.subprocess, "run") as run:
        tty_lockdown.lock_tty()
    calls = _systemctl_calls(run)
    masked_units = {c[2] for c in calls if c[:2] == ["systemctl", "mask"]}
    stopped_units = {c[2] for c in calls if c[:2] == ["systemctl", "stop"]}
    expected = {f"getty@tty{n}.service" for n in range(1, 7)} | {
        f"autovt@tty{n}.service" for n in range(1, 7)
    }
    assert masked_units == expected
    assert stopped_units == expected


def test_lock_tty_stops_before_masking() -> None:
    with patch.object(tty_lockdown.subprocess, "run") as run:
        tty_lockdown.lock_tty()
    seen_stops: set[str] = set()
    for call in run.call_args_list:
        argv = call.args[0]
        if argv[:2] == ["systemctl", "stop"]:
            seen_stops.add(argv[2])
        elif argv[:2] == ["systemctl", "mask"]:
            assert argv[2] in seen_stops, (
                f"{argv[2]} was masked before its getty was stopped"
            )


def test_lock_tty_writes_logind_dropin() -> None:
    with patch.object(tty_lockdown.subprocess, "run"):
        tty_lockdown.lock_tty()
    assert tty_lockdown._LOGIND_RUNTIME_DROPIN.exists()
    body = tty_lockdown._LOGIND_RUNTIME_DROPIN.read_text()
    assert "NAutoVTs=0" in body
    assert "ReserveVT=0" in body


def test_lock_tty_sighup_logind() -> None:
    with patch.object(tty_lockdown.subprocess, "run") as run:
        tty_lockdown.lock_tty()
    calls = _systemctl_calls(run)
    assert ["systemctl", "kill", "-s", "HUP", "systemd-logind.service"] in calls


def test_unlock_tty_unmasks_everything_and_removes_dropin() -> None:
    # Pre-create the drop-in so we can assert it's removed.
    tty_lockdown._LOGIND_RUNTIME_DROPIN_DIR.mkdir(parents=True, exist_ok=True)
    tty_lockdown._LOGIND_RUNTIME_DROPIN.write_text("stale\n")
    with patch.object(tty_lockdown.subprocess, "run") as run:
        tty_lockdown.unlock_tty()
    calls = _systemctl_calls(run)
    unmasked = {c[2] for c in calls if c[:2] == ["systemctl", "unmask"]}
    expected = {f"getty@tty{n}.service" for n in range(1, 7)} | {
        f"autovt@tty{n}.service" for n in range(1, 7)
    }
    assert unmasked == expected
    assert not tty_lockdown._LOGIND_RUNTIME_DROPIN.exists()


def test_lock_tty_survives_missing_systemctl() -> None:
    with patch.object(
        tty_lockdown.subprocess, "run",
        side_effect=FileNotFoundError("systemctl"),
    ):
        tty_lockdown.lock_tty()  # must not raise


def test_lock_tty_survives_timeout() -> None:
    import subprocess
    with patch.object(
        tty_lockdown.subprocess, "run",
        side_effect=subprocess.TimeoutExpired("systemctl", 5),
    ):
        tty_lockdown.lock_tty()  # must not raise


def test_unlock_tty_survives_missing_systemctl() -> None:
    with patch.object(
        tty_lockdown.subprocess, "run",
        side_effect=FileNotFoundError("systemctl"),
    ):
        tty_lockdown.unlock_tty()  # must not raise


def test_tty_active_watcher_fires_on_switch(tmp_path, monkeypatch) -> None:
    """The watcher should report a callback when /sys/class/tty/tty0/active changes."""
    active = tmp_path / "active"
    active.write_text("tty1\n")
    monkeypatch.setattr(tty_lockdown, "_TTY_ACTIVE_PATH", active)

    seen: list[tuple[str, str]] = []
    event = threading.Event()

    def on_switch(new_tty: str, baseline: str) -> None:
        seen.append((new_tty, baseline))
        event.set()

    watcher = tty_lockdown.TTYActiveWatcher(on_switch, poll_interval=0.05)
    watcher.start()
    try:
        time.sleep(0.1)  # let the baseline read settle
        active.write_text("tty3\n")
        assert event.wait(2.0), "watcher never fired"
    finally:
        watcher.stop()
    assert seen == [("tty3", "tty1")]


def test_tty_active_watcher_silent_when_idle(tmp_path, monkeypatch) -> None:
    active = tmp_path / "active"
    active.write_text("tty1\n")
    monkeypatch.setattr(tty_lockdown, "_TTY_ACTIVE_PATH", active)

    seen: list[tuple[str, str]] = []
    watcher = tty_lockdown.TTYActiveWatcher(
        lambda n, b: seen.append((n, b)), poll_interval=0.05,
    )
    watcher.start()
    try:
        time.sleep(0.2)
    finally:
        watcher.stop()
    assert seen == []


def test_tty_active_watcher_only_fires_once_per_target(tmp_path, monkeypatch) -> None:
    """Repeated polls while sitting on the same non-baseline VT should not spam."""
    active = tmp_path / "active"
    active.write_text("tty1\n")
    monkeypatch.setattr(tty_lockdown, "_TTY_ACTIVE_PATH", active)

    fired = threading.Event()
    calls: list[tuple[str, str]] = []

    def on_switch(new_tty: str, baseline: str) -> None:
        calls.append((new_tty, baseline))
        fired.set()

    watcher = tty_lockdown.TTYActiveWatcher(on_switch, poll_interval=0.05)
    watcher.start()
    try:
        time.sleep(0.1)
        active.write_text("tty2\n")
        assert fired.wait(2.0)
        time.sleep(0.25)  # poll several more times
    finally:
        watcher.stop()
    assert calls.count(("tty2", "tty1")) == 1


def test_tty_units_constant_is_concatenation() -> None:
    """Backstop the public list other code consults."""
    assert tty_lockdown.TTY_UNITS == tty_lockdown.GETTY_UNITS + tty_lockdown.AUTOVT_UNITS
    assert len(tty_lockdown.TTY_UNITS) == 12
