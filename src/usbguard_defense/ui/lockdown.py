"""Lockdown overlay — full-screen, always-on-top, blocks input.

v0.2.0: two new unlock paths (admin password + paper recovery code) are
exposed as buttons on the overlay. We grab the **keyboard** so other
applications can't receive keystrokes during lockdown, but we DO NOT
grab the mouse — `QWidget.grabMouse()` routes every mouse event to the
grabbing widget rather than its children, which made the unlock
buttons impossible to click. Fullscreen-on-top is sufficient to keep
the user inside the overlay visually; the keyboard grab keeps key
combos (Alt+Tab, Super, etc.) from escaping to other windows.

If the daemon accepts the unlock, the overlay is hidden by the main
window via lockdown_clear.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import (
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from .styles import LOCKDOWN_STYLE


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
        layout.setContentsMargins(80, 80, 80, 80)
        layout.setSpacing(28)
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

        layout.addSpacing(40)

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

        layout.addStretch(2)

    def show_for(self, offender: dict) -> None:
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
