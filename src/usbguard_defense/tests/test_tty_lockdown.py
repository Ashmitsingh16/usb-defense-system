"""Tests for the TTY lockdown helper.

`tty_lockdown` shells out to `systemctl mask` / `unmask` which doesn't
exist on Windows. We patch `subprocess.run` and assert on the argv it
was called with, so the module's intent is locked down without needing
a Linux host.
"""

from __future__ import annotations

from unittest.mock import patch

from usbguard_defense import tty_lockdown


def test_lock_tty_masks_all_five_consoles() -> None:
    with patch.object(tty_lockdown.subprocess, "run") as run:
        tty_lockdown.lock_tty()
    # 5 consoles × 2 calls (stop + mask) = 10 subprocess.run invocations.
    assert run.call_count == 10
    masked_units = {
        call.args[0][2] for call in run.call_args_list
        if call.args[0][:2] == ["systemctl", "mask"]
    }
    assert masked_units == {f"getty@tty{n}.service" for n in range(2, 7)}


def test_lock_tty_stops_before_masking() -> None:
    """If we mask without stopping first, the active getty keeps running."""
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


def test_unlock_tty_unmasks_all_five_consoles() -> None:
    with patch.object(tty_lockdown.subprocess, "run") as run:
        tty_lockdown.unlock_tty()
    assert run.call_count == 5
    unmasked = {
        call.args[0][2] for call in run.call_args_list
        if call.args[0][:2] == ["systemctl", "unmask"]
    }
    assert unmasked == {f"getty@tty{n}.service" for n in range(2, 7)}


def test_lock_tty_survives_missing_systemctl() -> None:
    """On a system without systemctl the call must not crash the daemon."""
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
