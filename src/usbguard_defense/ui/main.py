"""Main UI application — wires together dashboard, lockdown, whitelist, log, settings."""

from __future__ import annotations

import logging
import sys
from datetime import datetime

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
)

from .. import __version__
from ..config import load_config
from ..event_log import EventLogger
from ..ipc import IPCClient
from ..whitelist import Whitelist, WhitelistEntry
from .dashboard import DashboardWidget
from .event_log import EventLogWidget
from .lockdown import LockdownOverlay
from .settings import SettingsWidget
from .styles import DARK_THEME
from .whitelist_mgr import WhitelistManagerWidget


log = logging.getLogger("usb-defense-ui")


class IPCBridge(QObject):
    """Threading bridge: emits Qt signals when IPC events arrive on background thread."""

    event_received = pyqtSignal(dict)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"USB Defense System v{__version__}")
        self.setMinimumSize(960, 640)

        self.config = load_config()
        self.whitelist = Whitelist()
        self.event_logger = EventLogger()
        self.last_event_text = "—"

        self.bridge = IPCBridge()
        self.bridge.event_received.connect(self._on_daemon_event)
        self.ipc = IPCClient()
        self.ipc.on_event = self.bridge.event_received.emit

        # Build screens
        self.dashboard = DashboardWidget(
            on_open_whitelist=lambda: self._show(self.whitelist_screen),
            on_open_log=lambda: self._show(self.log_screen),
            on_open_settings=lambda: self._show(self.settings_screen),
        )
        self.whitelist_screen = WhitelistManagerWidget(
            get_entries=self._get_whitelist_dicts,
            add_entry=self._add_whitelist_entry,
            remove_entry=self._remove_whitelist_entry,
        )
        self.log_screen = EventLogWidget(get_events=self.event_logger.read_recent)
        self.settings_screen = SettingsWidget(
            config_dict=self.config.__dict__,
            on_save=self._save_settings,
        )

        self.stack = QStackedWidget()
        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.whitelist_screen)
        self.stack.addWidget(self.log_screen)
        self.stack.addWidget(self.settings_screen)
        self.setCentralWidget(self.stack)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Connecting to daemon…")

        self.lockdown_overlay = LockdownOverlay()

        # Try to connect to daemon
        self._connect_to_daemon()
        # Periodic dashboard refresh
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_dashboard)
        self.refresh_timer.start(2000)

    def _show(self, widget: QWidget) -> None:
        self.stack.setCurrentWidget(widget)

    def _connect_to_daemon(self) -> None:
        if self.ipc.connect():
            self.statusBar().showMessage("Connected to daemon")
            # Ask the daemon to dump its current state so we can sync our overlay
            # if the daemon was already in lockdown when we connected.
            self.ipc.send_command({"cmd": "status"})
        else:
            self.statusBar().showMessage("Daemon offline — whitelist still editable, but no enforcement")

    def _refresh_dashboard(self) -> None:
        # If we lost the daemon connection, try to re-establish it so the UI
        # recovers automatically after a daemon restart (no more stuck overlays).
        if not self.ipc.is_connected():
            if self.lockdown_overlay.isVisible():
                # We can't trust our overlay state once the daemon is gone — drop
                # it so we don't pin the user out of a system that isn't locked.
                self.lockdown_overlay.hide_overlay()
                self.dashboard.set_status_secure()
            self._connect_to_daemon()
        self.dashboard.update_stats(
            whitelist_count=len(self.whitelist.entries),
            daemon_running=self.ipc.is_connected(),
            last_event=self.last_event_text,
        )

    # ---- Event handlers (run in Qt main thread via signal bridge) ----
    def _on_daemon_event(self, event: dict) -> None:
        etype = event.get("type")
        if etype == "lockdown_enter":
            offender = event.get("offender", {})
            self.lockdown_overlay.show_for(offender)
            desc = f"{offender.get('manufacturer','?')} {offender.get('product','?')}"
            self.dashboard.set_status_locked(desc)
            self.last_event_text = f"{datetime.now():%H:%M:%S} LOCKDOWN — {desc}"
        elif etype == "lockdown_clear":
            self.lockdown_overlay.hide_overlay()
            self.dashboard.set_status_secure()
            self.last_event_text = f"{datetime.now():%H:%M:%S} unlocked"
        elif etype == "status":
            # Sync overlay to daemon's authoritative state. This fires on (re)connect
            # so we recover correctly if the daemon was already locked, or if the
            # daemon restarted while our UI was up.
            if event.get("locked"):
                self.lockdown_overlay.show_for(event.get("offender") or {})
                off = event.get("offender") or {}
                self.dashboard.set_status_locked(
                    f"{off.get('manufacturer','?')} {off.get('product','?')}"
                )
            else:
                if self.lockdown_overlay.isVisible():
                    self.lockdown_overlay.hide_overlay()
                    self.dashboard.set_status_secure()
        elif etype == "unauthorized_insert":
            d = event.get("device", {})
            desc = f"{d.get('manufacturer','?')} {d.get('product','?')}"
            self.dashboard.set_status_alert(desc)
            self.last_event_text = f"{datetime.now():%H:%M:%S} BLOCKED — {desc}"
        elif etype == "authorized_insert":
            d = event.get("device", {})
            label = event.get("label", "?")
            self.last_event_text = f"{datetime.now():%H:%M:%S} allowed: {label}"
        # Refresh log table if visible
        if self.stack.currentWidget() is self.log_screen:
            self.log_screen.refresh()

    # ---- Whitelist callbacks ----
    def _get_whitelist_dicts(self) -> list[dict]:
        from dataclasses import asdict
        self.whitelist._load()  # reload from disk
        return [asdict(e) for e in self.whitelist.entries]

    def _add_whitelist_entry(self, data: dict) -> None:
        entry = WhitelistEntry.new(
            label=data["label"],
            vendor_id=data["vendor_id"],
            product_id=data["product_id"],
            serial=data["serial"],
            device_class=data["device_class"],
            added_by="admin",
            can_unlock=data["can_unlock"],
        )
        self.whitelist.add(entry)

    def _remove_whitelist_entry(self, entry_id: str) -> None:
        self.whitelist.remove(entry_id)

    def _save_settings(self, new_dict: dict) -> None:
        # Persist to YAML
        import yaml
        from ..config import CONFIG_PATH
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with CONFIG_PATH.open("w") as fh:
                yaml.safe_dump(new_dict, fh)
            self.statusBar().showMessage("Settings saved", 4000)
        except OSError as exc:
            self.statusBar().showMessage(f"Save failed: {exc}", 4000)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_THEME)
    win = MainWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
