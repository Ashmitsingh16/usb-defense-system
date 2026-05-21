"""Settings UI."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QFormLayout, QLabel, QPushButton, QSlider, QSpinBox,
    QVBoxLayout, QWidget,
)


class SettingsWidget(QWidget):
    def __init__(self, config_dict: dict, on_save):
        super().__init__()
        self._config = dict(config_dict)
        self._on_save = on_save
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        heading = QLabel("Settings")
        heading.setObjectName("headingLabel")
        layout.addWidget(heading)

        form = QFormLayout()

        self.alarm_enabled = QCheckBox("Play audible alarm during lockdown")
        self.alarm_enabled.setChecked(self._config.get("alarm_enabled", True))
        form.addRow(self.alarm_enabled)

        self.alarm_volume = QSlider(Qt.Horizontal)
        self.alarm_volume.setRange(0, 100)
        self.alarm_volume.setValue(self._config.get("alarm_volume", 80))
        form.addRow("Alarm volume:", self.alarm_volume)

        self.grace_period = QSpinBox()
        self.grace_period.setRange(0, 60)
        self.grace_period.setSuffix(" seconds")
        self.grace_period.setValue(self._config.get("lockdown_grace_period_sec", 0))
        form.addRow("Lockdown grace period:", self.grace_period)

        self.require_unlock_key = QCheckBox(
            "Only USBs marked as 'unlock key' can clear lockdown")
        self.require_unlock_key.setChecked(self._config.get("require_unlock_key", True))
        form.addRow(self.require_unlock_key)

        self.notify_on_authorized = QCheckBox(
            "Show notification when an authorized USB is connected")
        self.notify_on_authorized.setChecked(self._config.get("notify_on_authorized", True))
        form.addRow(self.notify_on_authorized)

        layout.addLayout(form)

        save = QPushButton("Save Settings")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        layout.addWidget(save)
        layout.addStretch(1)

    def _save(self) -> None:
        self._config.update({
            "alarm_enabled": self.alarm_enabled.isChecked(),
            "alarm_volume": self.alarm_volume.value(),
            "lockdown_grace_period_sec": self.grace_period.value(),
            "require_unlock_key": self.require_unlock_key.isChecked(),
            "notify_on_authorized": self.notify_on_authorized.isChecked(),
        })
        self._on_save(self._config)
