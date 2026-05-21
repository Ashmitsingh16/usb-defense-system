"""Lockdown overlay — full-screen, always-on-top, blocks input."""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .styles import LOCKDOWN_STYLE


class LockdownOverlay(QWidget):
    """Modal full-screen widget shown during USB lockdown."""

    def __init__(self):
        super().__init__()
        self.setObjectName("lockdownRoot")
        self.setStyleSheet(LOCKDOWN_STYLE)
        flags = (
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus  # but we'll grabKeyboard ourselves
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
        self.showFullScreen()
        self.activateWindow()
        self.raise_()
        # Restart blink — hide_overlay stops it, so a re-show needs to kick it again.
        if not self._timer.isActive():
            self._timer.start(700)
        # Block keyboard from leaving this window
        self.grabKeyboard()
        self.grabMouse()

    def hide_overlay(self) -> None:
        self.releaseKeyboard()
        self.releaseMouse()
        self._timer.stop()
        self.hide()

    def _blink(self) -> None:
        self._blink_state = not self._blink_state
        self.title.setVisible(self._blink_state)

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        # Swallow all keypresses except a hidden admin escape (Ctrl+Shift+Alt+U)
        # Leave admin escape to a separate password dialog (not implemented here).
        ev.ignore()

    def closeEvent(self, ev) -> None:
        # Refuse to close — only daemon can unlock.
        ev.ignore()
