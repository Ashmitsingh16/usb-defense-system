"""Block TTY console escape during lockdown.

Default Rocky/RHEL has getty running on tty2..tty6. While the GUI lockdown
overlay is active, a curious user could press Ctrl+Alt+F3 to switch to a
text console and log in, sidestepping the overlay. This module masks those
getty units for the duration of the lockdown and restores them when the
lockdown clears.

The harder part — preventing the VT switch itself — is handled at install
time by dropping `Option "DontVTSwitch" "True"` into
/etc/X11/xorg.conf.d/, so combined we get defense in depth:
  - VT switch is blocked at the X server level.
  - Even if a user reaches a TTY (e.g., via crash recovery), no login
    prompt is presented.

All systemctl calls are best-effort: failure is logged and the lockdown
proceeds anyway, because crashing the daemon over a TTY-masking failure
would be worse than leaving the TTY available.
"""

from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)

TTY_UNITS = [f"getty@tty{n}.service" for n in range(2, 7)]


def lock_tty() -> None:
    for unit in TTY_UNITS:
        _run(["systemctl", "stop", unit])
        _run(["systemctl", "mask", unit])


def unlock_tty() -> None:
    for unit in TTY_UNITS:
        _run(["systemctl", "unmask", unit])


def _run(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=False, capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        log.warning("TTY lock command %s failed: %s", cmd[0], exc)
