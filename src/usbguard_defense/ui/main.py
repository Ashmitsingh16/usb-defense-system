"""Main UI application — wires dashboard, lockdown, whitelist, log, settings.

v0.2.0: the UI no longer writes the whitelist file directly. Add/remove
goes through the daemon's IPC layer with an admin password, and the
whitelist list is sourced from the daemon's `list_whitelist` response
rather than read from /etc/usb-defense/whitelist.json (which is now
0600 root and would not be readable by the UI process anyway).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QStackedWidget, QStatusBar,
)

from .. import __version__
from ..config import load_config
from ..event_log import EventLogger
from ..ipc import IPCClient
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
        self.event_logger = EventLogger()
        self.last_event_text = "—"

        # Cached whitelist (populated from daemon `list_whitelist` responses).
        # The UI never reads /etc/usb-defense/whitelist.json directly because
        # that file is 0600 root and the UI runs as a normal user.
        self._whitelist_cache: list[dict] = []

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
            get_entries=lambda: self._whitelist_cache,
            submit_add=self._submit_add_whitelist,
            submit_remove=self._submit_remove_whitelist,
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
        self.lockdown_overlay.unlock_with_password_requested.connect(
            self._submit_unlock_password
        )
        self.lockdown_overlay.unlock_with_seed_requested.connect(
            self._submit_unlock_seed
        )

        self._connect_to_daemon()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_dashboard)
        self.refresh_timer.start(2000)

    def _show(self, widget) -> None:
        self.stack.setCurrentWidget(widget)
        if widget is self.whitelist_screen:
            self._request_whitelist()

    def _connect_to_daemon(self) -> None:
        if self.ipc.connect():
            self.statusBar().showMessage("Connected to daemon")
            self.ipc.send_command({"cmd": "status"})
            self._request_whitelist()
        else:
            self.statusBar().showMessage(
                "Daemon offline — whitelist edits are disabled until the daemon is back"
            )

    def _request_whitelist(self) -> None:
        if self.ipc.is_connected():
            self.ipc.send_command({"cmd": "list_whitelist"})

    def _refresh_dashboard(self) -> None:
        if not self.ipc.is_connected():
            if self.lockdown_overlay.isVisible():
                self.lockdown_overlay.hide_overlay()
                self.dashboard.set_status_secure()
            self._connect_to_daemon()
        self.dashboard.update_stats(
            whitelist_count=len(self._whitelist_cache),
            daemon_running=self.ipc.is_connected(),
            last_event=self.last_event_text,
        )

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
            if event.get("warn_regenerate_seed"):
                QMessageBox.warning(
                    self, "Recovery code consumed",
                    "The paper recovery code was used to clear this lockdown "
                    "and has been INVALIDATED.\n\n"
                    "Generate a new one with:\n"
                    "    sudo python3 scripts/setup.py --regenerate-recovery"
                )
        elif etype == "status":
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
            if event.get("integrity_failed"):
                self.statusBar().showMessage(
                    "Whitelist tamper detected — daemon refusing to load entries"
                )
        elif etype == "whitelist_list":
            self._whitelist_cache = event.get("entries") or []
            self.whitelist_screen.refresh()
        elif etype == "whitelist_changed":
            self._request_whitelist()
        elif etype == "add_whitelist_entry":
            if event.get("ok"):
                self.whitelist_screen.show_status("Device added to whitelist.")
            else:
                err = event.get("error") or "unknown"
                msg = ("Wrong admin password." if err == "unauthorized"
                       else f"Add failed: {err}")
                self.whitelist_screen.show_status(msg, error=True)
        elif etype == "remove_whitelist_entry":
            if event.get("ok"):
                self.whitelist_screen.show_status("Device removed.")
            elif event.get("error") == "unauthorized":
                self.whitelist_screen.show_status("Wrong admin password.", error=True)
        elif etype == "unlock_with_password":
            if not event.get("ok"):
                self.lockdown_overlay.show_unlock_error(
                    "Wrong password — try again or use the paper code."
                )
        elif etype == "unlock_with_seed":
            if not event.get("ok"):
                self.lockdown_overlay.show_unlock_error(
                    "Code not accepted. Check for typos (O/0, I/L/1, U/V)."
                )
        elif etype == "unauthorized_insert":
            d = event.get("device", {})
            desc = f"{d.get('manufacturer','?')} {d.get('product','?')}"
            self.dashboard.set_status_alert(desc)
            self.last_event_text = f"{datetime.now():%H:%M:%S} BLOCKED — {desc}"
        elif etype == "authorized_insert":
            d = event.get("device", {})
            label = event.get("label", "?")
            self.last_event_text = f"{datetime.now():%H:%M:%S} allowed: {label}"
        if self.stack.currentWidget() is self.log_screen:
            self.log_screen.refresh()

    # ---- IPC submitters ----
    def _submit_add_whitelist(self, data: dict, password: str) -> None:
        if not self.ipc.is_connected():
            self.whitelist_screen.show_status(
                "Daemon is offline — cannot add.", error=True,
            )
            return
        self.ipc.send_command({
            "cmd": "add_whitelist_entry",
            "password": password,
            "entry": {**data, "added_by": "admin"},
        })

    def _submit_remove_whitelist(self, entry_id: str, password: str) -> None:
        if not self.ipc.is_connected():
            self.whitelist_screen.show_status(
                "Daemon is offline — cannot remove.", error=True,
            )
            return
        self.ipc.send_command({
            "cmd": "remove_whitelist_entry",
            "password": password,
            "entry_id": entry_id,
        })

    def _submit_unlock_password(self, password: str) -> None:
        if not self.ipc.is_connected():
            self.lockdown_overlay.show_unlock_error("Daemon offline.")
            return
        self.ipc.send_command({"cmd": "unlock_with_password", "password": password})

    def _submit_unlock_seed(self, code: str) -> None:
        if not self.ipc.is_connected():
            self.lockdown_overlay.show_unlock_error("Daemon offline.")
            return
        self.ipc.send_command({"cmd": "unlock_with_seed", "code": code})

    def _save_settings(self, new_dict: dict) -> None:
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
