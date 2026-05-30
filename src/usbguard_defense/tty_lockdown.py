"""Block TTY console escape during lockdown.

The previous version only masked ``getty@tty2..6``. That left two ways
out:

1. ``logind`` spawns text consoles through the ``autovt@.service``
   alias, not ``getty@``. Masking only ``getty@`` did not prevent
   logind from launching a fresh getty on the next VT-switch.
2. ``tty1`` was never covered. On a graphical-target boot tty1 hosts
   the X server, but a curious user can still ``chvt 1`` after killing
   X, or the system can boot into multi-user.target where tty1 is a
   plain login console.

v0.3.0 closes both:

- ``lock_tty()`` masks ``getty@tty1..6`` *and* ``autovt@tty1..6``, and
  also disables logind's pool of auto-VTs at runtime via a drop-in at
  ``/run/systemd/logind.conf.d/`` so newly-allocated VTs are blocked
  for the duration of the lockdown.
- A persistent drop-in is installed by ``install.sh`` so the protection
  survives a reboot mid-lockdown.
- ``TTYActiveWatcher`` polls ``/sys/class/tty/tty0/active`` every
  second while locked. Any change from the VT that was foreground at
  lockdown start is reported through the supplied callback as an
  intrusion attempt — so even a ``chvt`` from another root shell shows
  up timestamped in the UI.

All systemctl / file calls are best-effort: failure is logged and the
lockdown proceeds anyway, because crashing the daemon over a
TTY-masking failure would be worse than leaving the TTY available.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional


log = logging.getLogger(__name__)

# tty1..tty6 — tty1 is the graphical console on Rocky's default
# graphical target, the rest are text consoles served by logind on
# demand. We mask both the direct getty unit and the autovt alias that
# logind uses to spawn them.
_TTY_NUMBERS = range(1, 7)
GETTY_UNITS = [f"getty@tty{n}.service" for n in _TTY_NUMBERS]
AUTOVT_UNITS = [f"autovt@tty{n}.service" for n in _TTY_NUMBERS]
TTY_UNITS = GETTY_UNITS + AUTOVT_UNITS

_LOGIND_RUNTIME_DROPIN_DIR = Path("/run/systemd/logind.conf.d")
_LOGIND_RUNTIME_DROPIN = _LOGIND_RUNTIME_DROPIN_DIR / "50-usbdefense-lock.conf"
_LOGIND_DROPIN_BODY = (
    "# Written by usb-defense daemon while a lockdown is active.\n"
    "# Removed automatically on unlock.\n"
    "[Login]\n"
    "NAutoVTs=0\n"
    "ReserveVT=0\n"
)

_TTY_ACTIVE_PATH = Path("/sys/class/tty/tty0/active")


def lock_tty() -> None:
    """Mask every login getty and tell logind to stop allocating VTs."""
    for unit in TTY_UNITS:
        _run(["systemctl", "stop", unit])
        _run(["systemctl", "mask", unit])
    _write_logind_dropin()
    # SIGHUP makes logind reread its config without restarting (which
    # would log everyone out). Best-effort.
    _run(["systemctl", "kill", "-s", "HUP", "systemd-logind.service"])


def unlock_tty() -> None:
    """Reverse lock_tty()."""
    for unit in TTY_UNITS:
        _run(["systemctl", "unmask", unit])
    _remove_logind_dropin()
    _run(["systemctl", "kill", "-s", "HUP", "systemd-logind.service"])


def current_active_tty() -> str:
    """Return the name of the foreground VT (e.g. ``tty1``) or ``""``."""
    try:
        return _TTY_ACTIVE_PATH.read_text().strip()
    except OSError:
        return ""


class TTYActiveWatcher:
    """Background thread that watches ``/sys/class/tty/tty0/active``.

    On every change away from the baseline VT recorded at ``start()``
    the supplied callback is invoked with ``(new_tty, baseline_tty)``.
    The callback is called from the watcher thread; it must be quick
    and thread-safe. Subsequent flaps back to baseline do not fire
    again until a new differing VT is seen.
    """

    def __init__(
        self,
        on_switch: Callable[[str, str], None],
        poll_interval: float = 1.0,
    ) -> None:
        self._on_switch = on_switch
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._baseline: str = ""

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._baseline = current_active_tty()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="TTYActiveWatcher",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self) -> None:
        last_reported: str = ""
        while not self._stop.is_set():
            current = current_active_tty()
            if (
                current
                and current != self._baseline
                and current != last_reported
            ):
                try:
                    self._on_switch(current, self._baseline)
                except Exception:
                    log.exception("TTYActiveWatcher callback raised")
                last_reported = current
            elif current == self._baseline:
                last_reported = ""
            # Use Event.wait so we can be stopped promptly.
            if self._stop.wait(self._poll_interval):
                break


def _write_logind_dropin() -> None:
    try:
        _LOGIND_RUNTIME_DROPIN_DIR.mkdir(parents=True, exist_ok=True)
        _LOGIND_RUNTIME_DROPIN.write_text(_LOGIND_DROPIN_BODY)
    except OSError as exc:
        log.warning("Could not write logind drop-in: %s", exc)


def _remove_logind_dropin() -> None:
    try:
        _LOGIND_RUNTIME_DROPIN.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        log.warning("Could not remove logind drop-in: %s", exc)


def _run(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=False, capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        log.warning("TTY lock command %s failed: %s", cmd[0], exc)
