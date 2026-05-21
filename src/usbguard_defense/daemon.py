"""USB Defense daemon — entry point.

Watches USB events, enforces whitelist, triggers lockdown UI.
Runs as a systemd service. Must run as root to talk to USBGuard CLI.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time

from . import __version__
from .alarm import AlarmPlayer
from .config import (
    ASSETS_DIR,
    LOCKDOWN_FLAG,
    PERSISTENT_LOCKDOWN_FLAG,
    PID_FILE,
    RUNTIME_DIR,
    load_config,
)
from .event_log import EventLogger
from .ipc import IPCServer
from .monitor import USBEvent, USBMonitor
from .usbguard_iface import USBGuard
from .whitelist import Whitelist


log = logging.getLogger("usb-defense")


class Daemon:
    def __init__(self) -> None:
        self.config = load_config()
        self.whitelist = Whitelist()
        self.event_log = EventLogger()
        self.ipc = IPCServer()
        self.monitor = USBMonitor(self._on_usb_event)
        self.alarm = AlarmPlayer(
            sound_path=ASSETS_DIR / self.config.alarm_sound,
            volume=self.config.alarm_volume,
        )
        self.locked = False
        self.lock_offender: dict | None = None
        self._running = True

    def start(self) -> None:
        log.info("USB Defense daemon v%s starting", __version__)
        self._write_pid()
        self._restore_lockdown_if_needed()
        self.ipc.on_command = self._handle_ipc_command
        self.ipc.start()
        self.monitor.start()
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT, self._on_signal)
        log.info("Daemon ready. Watching for USB events.")
        while self._running:
            time.sleep(1)
        self._shutdown()

    def _on_signal(self, signum, frame) -> None:
        log.info("Received signal %d, shutting down", signum)
        self._running = False

    def _shutdown(self) -> None:
        self.monitor.stop()
        self.alarm.stop()
        self.ipc.stop()
        self._remove_pid()
        log.info("Daemon stopped")

    def _write_pid(self) -> None:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))

    def _remove_pid(self) -> None:
        try: PID_FILE.unlink()
        except FileNotFoundError: pass

    def _restore_lockdown_if_needed(self) -> None:
        """If we crashed while locked, re-enter lockdown on restart (paranoid mode)."""
        if not PERSISTENT_LOCKDOWN_FLAG.exists():
            return
        log.warning("Found persistent lockdown flag — entering lockdown on startup")
        self.locked = True
        # Try to recover the offender dict from the flag payload. Legacy flags
        # (0.1.2 and earlier) contain the bare string "active\n"; in that case
        # we have no offender details and the UI will show "?" placeholders
        # until a fresh event arrives. That's documented as PERSIST-1 honest
        # behaviour, not a bug.
        try:
            payload = json.loads(PERSISTENT_LOCKDOWN_FLAG.read_text())
        except (json.JSONDecodeError, ValueError, OSError):
            payload = None
        if isinstance(payload, dict):
            self.lock_offender = payload.get("offender")
        LOCKDOWN_FLAG.write_text("restored\n")

    def _on_usb_event(self, event: USBEvent) -> None:
        log.info("USB event: %s %s", event.action, event.short_desc())
        if event.action == "add":
            self._handle_insert(event)
        elif event.action == "remove":
            self._handle_remove(event)

    def _handle_insert(self, event: USBEvent) -> None:
        match = self.whitelist.match(event.vendor_id, event.product_id, event.serial)
        event_dict = self._event_to_dict(event)

        if match is not None:
            # Authorized device
            self.event_log.write("AUTHORIZED", {**event_dict, "label": match.label})
            log.info("AUTHORIZED USB inserted: %s (%s)", match.label, event.fingerprint())
            self._allow_in_usbguard(event)
            self.ipc.broadcast({
                "type": "authorized_insert",
                "device": event_dict,
                "label": match.label,
                "can_unlock": match.can_unlock,
            })
            # If currently locked and this device can unlock, clear lockdown
            if self.locked and (match.can_unlock or not self.config.require_unlock_key):
                self._clear_lockdown(reason="authorized USB inserted",
                                     unlock_device=event_dict)
            return

        # Unauthorized device
        self.event_log.write("UNAUTHORIZED", event_dict)
        log.warning("UNAUTHORIZED USB inserted: %s", event.short_desc())
        self._block_in_usbguard(event)
        self.ipc.broadcast({
            "type": "unauthorized_insert",
            "device": event_dict,
        })
        if self.config.auto_block_unknown:
            self._enter_lockdown(event_dict)

    def _handle_remove(self, event: USBEvent) -> None:
        self.event_log.write("REMOVE", self._event_to_dict(event))
        self.ipc.broadcast({
            "type": "remove",
            "device": self._event_to_dict(event),
        })

    def _enter_lockdown(self, offender: dict) -> None:
        if self.locked:
            return
        self.locked = True
        self.lock_offender = offender
        log.warning("ENTERING LOCKDOWN due to %s", offender.get("fingerprint"))
        # Persist flag so we restore on crash. Payload is a JSON dict so that
        # a daemon coming back from a kill can recover the offender details
        # (and the UI's "?" placeholders go away). Backwards-readable by the
        # 0.1.2 restore path, which simply ignored the contents.
        PERSISTENT_LOCKDOWN_FLAG.parent.mkdir(parents=True, exist_ok=True)
        flag_payload = json.dumps({"locked": True, "offender": offender}) + "\n"
        PERSISTENT_LOCKDOWN_FLAG.write_text(flag_payload)
        LOCKDOWN_FLAG.write_text("active\n")
        # Tell UI
        self.ipc.broadcast({"type": "lockdown_enter", "offender": offender})
        # Start alarm
        if self.config.alarm_enabled:
            self.alarm.start()

    def _clear_lockdown(self, reason: str, unlock_device: dict | None = None) -> None:
        if not self.locked:
            return
        self.locked = False
        self.lock_offender = None
        log.info("Lockdown cleared: %s", reason)
        self.alarm.stop()
        try: PERSISTENT_LOCKDOWN_FLAG.unlink()
        except FileNotFoundError: pass
        try: LOCKDOWN_FLAG.unlink()
        except FileNotFoundError: pass
        self.ipc.broadcast({
            "type": "lockdown_clear",
            "reason": reason,
            "unlock_device": unlock_device,
        })

    def _allow_in_usbguard(self, event: USBEvent) -> None:
        d = USBGuard.find_by_fingerprint(event.vendor_id, event.product_id, event.serial)
        if d is not None:
            USBGuard.allow_device(d.device_id)

    def _block_in_usbguard(self, event: USBEvent) -> None:
        d = USBGuard.find_by_fingerprint(event.vendor_id, event.product_id, event.serial)
        if d is not None:
            USBGuard.block_device(d.device_id)

    @staticmethod
    def _event_to_dict(event: USBEvent) -> dict:
        return {
            "vendor_id": event.vendor_id,
            "product_id": event.product_id,
            "serial": event.serial,
            "fingerprint": event.fingerprint(),
            "device_class": event.device_class_name,
            "manufacturer": event.manufacturer,
            "product": event.product,
            "usb_version": event.usb_version,
            "capacity_bytes": event.capacity_bytes,
            "devnode": event.devnode,
        }

    def _handle_ipc_command(self, msg: dict) -> dict:
        cmd = msg.get("cmd")
        if cmd == "status":
            return {
                "type": "status",
                "locked": self.locked,
                "offender": self.lock_offender,
                "whitelist_size": len(self.whitelist.entries),
                "version": __version__,
            }
        if cmd == "list_whitelist":
            from dataclasses import asdict
            return {"entries": [asdict(e) for e in self.whitelist.entries]}
        if cmd == "force_unlock":
            # Admin-authenticated unlock, e.g., authorized_admin_password verified by UI
            if msg.get("admin_token") == os.environ.get("USB_DEFENSE_ADMIN_TOKEN"):
                self._clear_lockdown(reason="admin force unlock")
                return {"ok": True}
            return {"error": "unauthorized"}
        if cmd == "simulate_event":
            # Re-broadcast a synthetic event to every connected UI client so the
            # lockdown / dashboard flow can be exercised without real hardware.
            payload = msg.get("event") or {}
            ptype = payload.get("type")
            if ptype == "lockdown_enter":
                self._enter_lockdown(payload.get("offender") or {})
            elif ptype == "lockdown_clear":
                self._clear_lockdown(reason=payload.get("reason") or "simulated unlock")
            elif ptype == "authorized_insert":
                # Mirror real-insert unlock logic so Demo 3 (asymmetric unlock)
                # can be exercised without real hardware: a can_unlock=True device
                # clears an active lockdown; can_unlock=False does not.
                self.ipc.broadcast(payload)
                if self.locked and (payload.get("can_unlock")
                                    or not self.config.require_unlock_key):
                    self._clear_lockdown(
                        reason="authorized USB (simulated) inserted",
                        unlock_device=payload.get("device"),
                    )
            else:
                self.ipc.broadcast(payload)
            return {"ok": True, "simulated": ptype}
        return {"error": f"unknown command: {cmd}"}


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stderr,
    )
    daemon = Daemon()
    daemon.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
