"""Plays alarm sound on lockdown. Stops on demand.

Uses `aplay` (ALSA) by default because the daemon runs as root in a systemd
context and has no user PulseAudio/PipeWire session to attach to. `paplay`
is kept as a fall-back for desktop testing where the daemon happens to run
inside a user session.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Optional


log = logging.getLogger(__name__)


class AlarmPlayer:
    """Loops a sound file until stopped. Prefers aplay (ALSA), falls back to paplay."""

    def __init__(self, sound_path: Path, volume: int = 80):
        self.sound_path = sound_path
        self.volume = max(0, min(100, volume))
        self._process: Optional[subprocess.Popen] = None
        self._set_master_volume()

    def _set_master_volume(self) -> None:
        """Best-effort: bump the system mixer so the alarm is audible.

        Failures are ignored — many headless installs lack `amixer` and the
        alarm still works, just at whatever volume the system has set.
        """
        if shutil.which("amixer") is None:
            return
        try:
            subprocess.run(
                ["amixer", "-q", "sset", "Master", f"{self.volume}%"],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=2,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    def _build_player_cmd(self) -> Optional[list[str]]:
        """Pick the best available CLI player; None if nothing is installed."""
        if shutil.which("aplay"):
            # aplay is ALSA, works as root with no user session
            inner = f'aplay -q "{self.sound_path}"'
        elif shutil.which("paplay"):
            pa_volume = int((self.volume / 100.0) * 65536)
            inner = f'paplay --volume={pa_volume} "{self.sound_path}"'
        else:
            return None
        return ["bash", "-c", f"while true; do {inner}; done"]

    def start(self) -> None:
        if self._process and self._process.poll() is None:
            return  # Already playing
        if not self.sound_path.exists():
            log.error("Alarm sound missing: %s", self.sound_path)
            return
        cmd = self._build_player_cmd()
        if cmd is None:
            log.error("Neither aplay nor paplay is installed — cannot play alarm")
            return
        try:
            self._process = subprocess.Popen(
                cmd,
                preexec_fn=os.setsid,  # so we can kill the whole group
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log.info("Alarm started (pid=%s) via %s", self._process.pid, cmd[2].split()[0])
        except FileNotFoundError:
            log.error("Audio player not found at runtime")

    def stop(self) -> None:
        if self._process and self._process.poll() is None:
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                self._process.wait(timeout=2)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            log.info("Alarm stopped")
        self._process = None

    def is_playing(self) -> bool:
        return self._process is not None and self._process.poll() is None
