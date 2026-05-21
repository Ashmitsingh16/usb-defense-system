"""Dashboard — main status screen."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)


class DashboardWidget(QWidget):
    def __init__(self, on_open_whitelist, on_open_log, on_open_settings):
        super().__init__()
        self._build(on_open_whitelist, on_open_log, on_open_settings)
        self.set_status_secure()
        self._whitelist_count = 0

    def _build(self, on_whitelist, on_log, on_settings) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        heading = QLabel("USB Defense System")
        heading.setObjectName("headingLabel")
        outer.addWidget(heading)

        sub = QLabel("Hardened workstation USB whitelist enforcement")
        sub.setObjectName("subheadingLabel")
        outer.addWidget(sub)

        # Status card
        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QVBoxLayout(status_card)
        self.status_label = QLabel("LOADING…")
        self.status_label.setObjectName("statusOK")
        status_layout.addWidget(self.status_label)
        self.status_detail = QLabel("Connecting to daemon…")
        status_layout.addWidget(self.status_detail)
        outer.addWidget(status_card)

        # Stats card
        stats_card = QFrame()
        stats_card.setObjectName("card")
        stats_layout = QHBoxLayout(stats_card)
        self.whitelist_count_label = QLabel("Whitelisted: --")
        self.daemon_state_label = QLabel("Daemon: --")
        self.last_event_label = QLabel("Last event: --")
        stats_layout.addWidget(self.whitelist_count_label)
        stats_layout.addStretch(1)
        stats_layout.addWidget(self.daemon_state_label)
        stats_layout.addStretch(1)
        stats_layout.addWidget(self.last_event_label)
        outer.addWidget(stats_card)

        # Action buttons
        btn_row = QHBoxLayout()
        b1 = QPushButton("Manage Whitelist")
        b1.setObjectName("primary")
        b1.clicked.connect(on_whitelist)
        b2 = QPushButton("View Event Log")
        b2.clicked.connect(on_log)
        b3 = QPushButton("Settings")
        b3.clicked.connect(on_settings)
        btn_row.addWidget(b1)
        btn_row.addWidget(b2)
        btn_row.addWidget(b3)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)
        outer.addStretch(1)

    def _repolish(self, label) -> None:
        # Qt does not re-evaluate the stylesheet after a setObjectName change
        # unless we explicitly unpolish + polish the widget.
        label.style().unpolish(label)
        label.style().polish(label)
        label.update()

    def set_status_secure(self) -> None:
        self.status_label.setText("● SYSTEM SECURE")
        self.status_label.setObjectName("statusOK")
        self._repolish(self.status_label)
        self.status_detail.setText("All connected USB devices are authorized.")

    def set_status_alert(self, offender_desc: str) -> None:
        self.status_label.setText("● UNAUTHORIZED USB BLOCKED")
        self.status_label.setObjectName("statusAlert")
        self._repolish(self.status_label)
        self.status_detail.setText(f"Last offender: {offender_desc}")

    def set_status_locked(self, offender_desc: str) -> None:
        self.status_label.setText("● SYSTEM LOCKED")
        self.status_label.setObjectName("statusAlert")
        self._repolish(self.status_label)
        self.status_detail.setText(f"Triggered by: {offender_desc}")

    def update_stats(self, whitelist_count: int, daemon_running: bool, last_event: str) -> None:
        self.whitelist_count_label.setText(f"Whitelisted: {whitelist_count}")
        self.daemon_state_label.setText(f"Daemon: {'running' if daemon_running else 'stopped'}")
        self.last_event_label.setText(f"Last event: {last_event}")
