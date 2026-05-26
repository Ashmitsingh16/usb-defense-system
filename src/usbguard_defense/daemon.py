"""USB Defense daemon — entry point.

Watches USB events, enforces the whitelist, triggers lockdown UI.
Runs as a systemd service. Must run as root.

v0.2.0 hardening:
- HMAC-signed whitelist via integrity.ensure_master_key(); whitelist
  load failure → fail closed (no entries trusted, every USB → lockdown).
- IPC commands `add_whitelist_entry`, `remove_whitelist_entry`,
  `unlock_with_password`, `unlock_with_seed` require a verified
  admin password (or paper code). The legacy `force_unlock` env-var
  trapdoor is removed.
- sd_notify integration: READY/WATCHDOG/STOPPING so systemd can
  detect daemon hangs and restart.
- TTY VT-switch escape blocked during active lockdown via
  tty_lockdown.lock_tty().
"""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import sys
import threading
import time
from dataclasses import asdict

from . import __version__
from .alarm import AlarmPlayer
from .auth import verify_admin_password
from .config import (
    ASSETS_DIR,
    LOCKDOWN_FLAG,
    PERSISTENT_LOCKDOWN_FLAG,
    PID_FILE,
    RUNTIME_DIR,
    load_config,
)
from .event_log import EventLogger
from .integrity import ensure_master_key
from .ipc import IPCServer
from .monitor import USBEvent, USBMonitor
from .recovery import verify_and_consume
from .tty_lockdown import lock_tty, unlock_tty
from .usbguard_iface import USBGuard
from .whitelist import Whitelist, WhitelistEntry


log = logging.getLogger("usb-defense")


def _sd_notify(message: str) -> None:
    """Minimal inline sd_notify so we don't pull in another dependency."""
    sock_path = os.environ.get("NOTIFY_SOCKET")
    if not sock_path:
        return
    if sock_path.startswith("@"):
        sock_path = "\0" + sock_path[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.sendto(message.encode("utf-8"), sock_path)
    except OSError as exc:
        log.debug("sd_notify failed: %s", exc)


class Daemon:
    def __init__(self) -> None:
        self.config = load_config()
        try:
            self.master_key: bytes | None = ensure_master_key()
        except Exception as exc:
            log.error(
                "Cannot load master key: %s. Whitelist integrity check "
                "DISABLED — running in degraded mode.", exc,
            )
            self.master_key = None
        self.whitelist = Whitelist(master_key=self.master_key)
        if self.whitelist.integrity_failed:
            log.error(
                "WHITELIST TAMPER DETECTED on startup — every USB will be "
                "treated as unauthorized until the whitelist is re-signed."
            )
        self.event_log = EventLogger()
        if self.whitelist.integrity_failed:
            self.event_log.write("WHITELIST_TAMPER", {"detected_at": "startup"})
        self.ipc = IPCServer()
        self.monitor = USBMonitor(self._on_usb_event)
        self.alarm = AlarmPlayer(
            sound_path=ASSETS_DIR / self.config.alarm_sound,
            volume=self.config.alarm_volume,
        )
        self.locked = False
        self.lock_offender: dict | None = None
        self._running = True
        self._watchdog_thread: threading.Thread | None = None

    def start(self) -> None:
        log.info("USB Defense daemon v%s starting", __version__)
        self._write_pid()
        self._restore_lockdown_if_needed()
        self.ipc.on_command = self._handle_ipc_command
        self.ipc.start()
        self.monitor.start()
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT, self._on_signal)
        _sd_notify("READY=1")
        log.info("Daemon ready. Watching for USB events.")
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="WatchdogPing",
        )
        self._watchdog_thread.start()
        while self._running:
            time.sleep(1)
        _sd_notify("STOPPING=1")
        self._shutdown()

    def _watchdog_loop(self) -> None:
        # WatchdogSec=30 in the unit, so ping every 10s.
        while self._running:
            _sd_notify("WATCHDOG=1")
            time.sleep(10)

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
        """If we crashed while locked, re-enter lockdown on restart."""
        if not PERSISTENT_LOCKDOWN_FLAG.exists():
            return
        log.warning("Found persistent lockdown flag — entering lockdown on startup")
        self.locked = True
        try:
            payload = json.loads(PERSISTENT_LOCKDOWN_FLAG.read_text())
        except (json.JSONDecodeError, ValueError, OSError):
            payload = None
        if isinstance(payload, dict):
            self.lock_offender = payload.get("offender")
        LOCKDOWN_FLAG.write_text("restored\n")
        # Re-apply TTY mask since we're back in lockdown
        lock_tty()

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
            self.event_log.write("AUTHORIZED", {**event_dict, "label": match.label})
            log.info("AUTHORIZED USB inserted: %s (%s)", match.label, event.fingerprint())
            self._allow_in_usbguard(event)
            self.ipc.broadcast({
                "type": "authorized_insert",
                "device": event_dict,
                "label": match.label,
                "can_unlock": match.can_unlock,
            })
            if self.locked and (match.can_unlock or not self.config.require_unlock_key):
                self._clear_lockdown(reason="authorized USB inserted",
                                     unlock_device=event_dict)
            return

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
        PERSISTENT_LOCKDOWN_FLAG.parent.mkdir(parents=True, exist_ok=True)
        flag_payload = json.dumps({"locked": True, "offender": offender}) + "\n"
        PERSISTENT_LOCKDOWN_FLAG.write_text(flag_payload)
        LOCKDOWN_FLAG.write_text("active\n")
        self.ipc.broadcast({"type": "lockdown_enter", "offender": offender})
        if self.config.alarm_enabled:
            self.alarm.start()
        lock_tty()

    def _clear_lockdown(self, reason: str, unlock_device: dict | None = None,
                        warn_regenerate_seed: bool = False) -> None:
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
        unlock_tty()
        self.ipc.broadcast({
            "type": "lockdown_clear",
            "reason": reason,
            "unlock_device": unlock_device,
            "warn_regenerate_seed": warn_regenerate_seed,
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

    def _check_password(self, msg: dict) -> bool:
        pw = msg.get("password")
        if not isinstance(pw, str) or not pw:
            return False
        try:
            return verify_admin_password(pw)
        except Exception as exc:
            log.error("Password verify error: %s", exc)
            return False

    def _handle_ipc_command(self, msg: dict) -> dict:
        cmd = msg.get("cmd")
        if cmd == "status":
            return {
                "type": "status",
                "locked": self.locked,
                "offender": self.lock_offender,
                "whitelist_size": len(self.whitelist.entries),
                "integrity_failed": self.whitelist.integrity_failed,
                "version": __version__,
            }
        if cmd == "list_whitelist":
            return {
                "type": "whitelist_list",
                "entries": [asdict(e) for e in self.whitelist.entries],
            }
        if cmd == "verify_password":
            return {"type": "verify_password", "ok": self._check_password(msg)}
        if cmd == "add_whitelist_entry":
            if not self._check_password(msg):
                self.event_log.write("AUTH_FAILURE", {"op": "add_whitelist_entry"})
                return {"type": "add_whitelist_entry", "ok": False, "error": "unauthorized"}
            entry_data = msg.get("entry") or {}
            try:
                entry = WhitelistEntry.new(
                    label=entry_data.get("label", "Unlabeled"),
                    vendor_id=entry_data.get("vendor_id", ""),
                    product_id=entry_data.get("product_id", ""),
                    serial=entry_data.get("serial", ""),
                    device_class=entry_data.get("device_class", "Unknown"),
                    added_by=entry_data.get("added_by", "admin"),
                    can_unlock=bool(entry_data.get("can_unlock", False)),
                )
            except (TypeError, ValueError) as exc:
                return {"type": "add_whitelist_entry", "ok": False, "error": str(exc)}
            self.whitelist.add(entry)
            self.event_log.write("WHITELIST_ADD", {"entry_id": entry.id, "label": entry.label})
            self.ipc.broadcast({"type": "whitelist_changed"})
            return {"type": "add_whitelist_entry", "ok": True, "entry_id": entry.id}
        if cmd == "remove_whitelist_entry":
            if not self._check_password(msg):
                self.event_log.write("AUTH_FAILURE", {"op": "remove_whitelist_entry"})
                return {"type": "remove_whitelist_entry", "ok": False, "error": "unauthorized"}
            entry_id = msg.get("entry_id", "")
            removed = self.whitelist.remove(entry_id)
            if removed:
                self.event_log.write("WHITELIST_REMOVE", {"entry_id": entry_id})
                self.ipc.broadcast({"type": "whitelist_changed"})
            return {"type": "remove_whitelist_entry", "ok": removed}
        if cmd == "unlock_with_password":
            if not self._check_password(msg):
                self.event_log.write("UNLOCK_AUTH_FAILURE", {"method": "password"})
                return {"type": "unlock_with_password", "ok": False}
            self.event_log.write("UNLOCK_SUCCESS", {"method": "password"})
            self._clear_lockdown(reason="admin password")
            return {"type": "unlock_with_password", "ok": True}
        if cmd == "unlock_with_seed":
            code = msg.get("code", "")
            if not isinstance(code, str) or not verify_and_consume(code):
                self.event_log.write("UNLOCK_AUTH_FAILURE", {"method": "paper_code"})
                return {"type": "unlock_with_seed", "ok": False}
            self.event_log.write("UNLOCK_SUCCESS", {"method": "paper_code"})
            self._clear_lockdown(
                reason="paper recovery code",
                warn_regenerate_seed=True,
            )
            return {"type": "unlock_with_seed", "ok": True}
        if cmd == "simulate_event":
            if not self.config.simulator_enabled:
                self.event_log.write("SIMULATOR_BLOCKED", {"reason": "disabled in config"})
                return {"error": "simulator disabled by config"}
            payload = msg.get("event") or {}
            ptype = payload.get("type")
            if ptype == "lockdown_enter":
                self._enter_lockdown(payload.get("offender") or {})
            elif ptype == "lockdown_clear":
                self._clear_lockdown(reason=payload.get("reason") or "simulated unlock")
            elif ptype == "authorized_insert":
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
