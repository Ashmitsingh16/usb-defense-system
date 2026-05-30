"""Lockdown overlay — full-screen, always-on-top, blocks input.

v0.2.0: two new unlock paths (admin password + paper recovery code) are
exposed as buttons on the overlay. We grab the **keyboard** so other
applications can't receive keystrokes during lockdown, but we DO NOT
grab the mouse — ``QWidget.grabMouse()`` routes every mouse event to
the grabbing widget rather than its children, which made the unlock
buttons impossible to click. Fullscreen-on-top is sufficient to keep
the user inside the overlay visually; the keyboard grab keeps key
combos (Alt+Tab, Super, etc.) from escaping to other windows.

v0.3.0: an intrusion timeline is rendered below the unlock buttons.
The daemon sends an ``intrusion_attempt`` IPC event for every wrong
password, wrong recovery code, USB re-insert, and TTY-switch attempt
detected during the lockdown. Each is shown with a local-time stamp
(HH:MM:SS) so the operator — and the panel watching the projector —
can see exactly when each attempt was made.

If the daemon accepts the unlock, the overlay is hidden by the main
window via lockdown_clear.
"""

from __future__ import annotations

from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from .styles import LOCKDOWN_STYLE


_KIND_LABELS = {
    "WRONG_PASSWORD": "Wrong admin password",
    "WRONG_RECOVERY_CODE": "Wrong recovery code",
    "USB_RETRY": "Unauthorized USB re-insert",
    "TTY_SWITCH": "Console (TTY) switch attempt",
}

# Limit to keep the overlay readable on a small screen. Older entries
# are still in the daemon's append-only event log; the overlay just
# scrolls to the newest.
_MAX_TIMELINE_ROWS = 200


class LockdownOverlay(QWidget):
    """Modal full-screen widget shown during USB lockdown."""

    unlock_with_password_requested = pyqtSignal(str)
    unlock_with_seed_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("lockdownRoot")
        self.setStyleSheet(LOCKDOWN_STYLE)
        flags = (
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self._build()
        self._blink_state = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._blink)
        self._timer.start(700)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 60, 80, 60)
        layout.setSpacing(20)
        layout.addStretch(1)

        self.title = QLabel("⚠  SYSTEM LOCKED  ⚠")
        self.title.setObjectName("lockdownTitle")
        layout.addWidget(self.title)

        self.subtitle = QLabel("UNAUTHORIZED USB DEVICE DETECTED")
        self.subtitle.setObjectName("lockdownSubtitle")
        layout.addWidget(self.subtitle)

        self.device_label = QLabel("")
        self.device_label.setObjectName("lockdownDevice")
        layout.addWidget(self.device_label)

        self.started_label = QLabel("")
        self.started_label.setObjectName("lockdownStarted")
        layout.addWidget(self.started_label)

        layout.addSpacing(20)

        self.prompt = QLabel("INSERT AUTHORIZED USB KEY TO UNLOCK")
        self.prompt.setObjectName("lockdownPrompt")
        layout.addWidget(self.prompt)

        self.error_label = QLabel("")
        self.error_label.setObjectName("lockdownError")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.password_btn = QPushButton("Unlock with admin password")
        self.password_btn.setObjectName("lockdownButton")
        self.password_btn.clicked.connect(self._on_password_clicked)
        button_row.addWidget(self.password_btn)
        self.seed_btn = QPushButton("Unlock with paper recovery code")
        self.seed_btn.setObjectName("lockdownButton")
        self.seed_btn.clicked.connect(self._on_seed_clicked)
        button_row.addWidget(self.seed_btn)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        # ---- Intrusion timeline ----
        self.timeline_frame = QFrame()
        self.timeline_frame.setObjectName("lockdownTimeline")
        timeline_layout = QVBoxLayout(self.timeline_frame)
        timeline_layout.setContentsMargins(16, 12, 16, 12)
        timeline_layout.setSpacing(6)
        self.timeline_header = QLabel("Intrusion attempts during this lockdown")
        self.timeline_header.setObjectName("lockdownTimelineHeader")
        timeline_layout.addWidget(self.timeline_header)
        self.timeline_list = QListWidget()
        self.timeline_list.setObjectName("lockdownTimelineList")
        self.timeline_list.setFocusPolicy(Qt.NoFocus)
        self.timeline_list.setSelectionMode(QListWidget.NoSelection)
        timeline_layout.addWidget(self.timeline_list, 1)
        self.timeline_empty = QLabel("No tampering attempts recorded yet.")
        self.timeline_empty.setObjectName("lockdownTimelineEmpty")
        timeline_layout.addWidget(self.timeline_empty)
        layout.addWidget(self.timeline_frame, 1)

        layout.addStretch(1)

    def show_for(self, offender: dict, started_at_iso: str | None = None) -> None:
        desc = (
            f"{offender.get('manufacturer','?')} "
            f"{offender.get('product','?')}\n"
            f"VID:PID = {offender.get('vendor_id','?')}:{offender.get('product_id','?')}    "
            f"Serial = {offender.get('serial','?')}\n"
            f"Class = {offender.get('device_class','?')}    "
            f"USB = {offender.get('usb_version','?')}"
        )
        self.device_label.setText(desc)
        self.error_label.setVisible(False)
        self.started_label.setText(self._format_started_at(started_at_iso))
        # Fresh lockdown session = fresh timeline. (When the UI
        # re-attaches mid-lockdown the main window also re-hydrates
        # any prior attempts from the persistent event log.)
        self.timeline_list.clear()
        self.timeline_empty.setVisible(True)
        self.showFullScreen()
        self.activateWindow()
        self.raise_()
        if not self._timer.isActive():
            self._timer.start(700)
        self.grabKeyboard()

    def hide_overlay(self) -> None:
        self.releaseKeyboard()
        self._timer.stop()
        self.hide()

    def show_unlock_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)

    def record_intrusion(self, kind: str, detail: str, iso_ts: str) -> None:
        """Append a single intrusion-attempt row to the timeline."""
        local = _iso_to_local_hms(iso_ts)
        label = _KIND_LABELS.get(kind, kind.replace("_", " ").title())
        item = QListWidgetItem(f"[{local}]  {label} — {detail}")
        self.timeline_list.addItem(item)
        # Trim from the top so we don't grow unbounded across long
        # lockdowns (e.g. an attacker hammering wrong passwords).
        while self.timeline_list.count() > _MAX_TIMELINE_ROWS:
            self.timeline_list.takeItem(0)
        self.timeline_list.scrollToBottom()
        self.timeline_empty.setVisible(False)

    def _format_started_at(self, started_at_iso: str | None) -> str:
        if not started_at_iso:
            return ""
        local = _iso_to_local_full(started_at_iso)
        if not local:
            return ""
        return f"Locked since {local}"

    def _blink(self) -> None:
        self._blink_state = not self._blink_state
        self.title.setVisible(self._blink_state)

    def _on_password_clicked(self) -> None:
        # Release the keyboard grab so the input dialog can receive
        # typing; re-grab on dialog dismiss regardless of outcome.
        self.releaseKeyboard()
        try:
            pw, ok = QInputDialog.getText(
                self, "Admin Unlock", "Enter admin password:",
                QLineEdit.Password,
            )
        finally:
            self.grabKeyboard()
        if ok and pw:
            self.error_label.setVisible(False)
            self.unlock_with_password_requested.emit(pw)

    def _on_seed_clicked(self) -> None:
        self.releaseKeyboard()
        try:
            code, ok = QInputDialog.getText(
                self, "Paper Recovery Code",
                "Enter the 16-character recovery code (hyphens optional):",
            )
        finally:
            self.grabKeyboard()
        if ok and code:
            self.error_label.setVisible(False)
            self.unlock_with_seed_requested.emit(code)

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        # Swallow all keypresses while locked.
        ev.ignore()

    def closeEvent(self, ev) -> None:
        # Refuse to close — only daemon can unlock.
        ev.ignore()


def _iso_to_local_hms(iso_ts: str) -> str:
    """Format an ISO-8601 UTC timestamp as local HH:MM:SS."""
    parsed = _parse_iso(iso_ts)
    if parsed is None:
        return iso_ts or "??:??:??"
    return parsed.astimezone().strftime("%H:%M:%S")


def _iso_to_local_full(iso_ts: str) -> str:
    """Format an ISO-8601 UTC timestamp as local YYYY-MM-DD HH:MM:SS."""
    parsed = _parse_iso(iso_ts)
    if parsed is None:
        return ""
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _parse_iso(iso_ts: str) -> datetime | None:
    if not iso_ts:
        return None
    try:
        return datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
