"""Whitelist management UI.

v0.2.0: add/remove now goes through the daemon over IPC and requires the
admin password. The widget prompts for the password, then hands data +
password to a caller-supplied submit_add / submit_remove callable. The
caller (MainWindow) is responsible for actually sending the IPC command
and refreshing the list on success.
"""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)


class WhitelistManagerWidget(QWidget):
    """Lists whitelist; supports add/remove via daemon over IPC."""

    def __init__(self, get_entries: Callable[[], list[dict]],
                 submit_add: Callable[[dict, str], None],
                 submit_remove: Callable[[str, str], None]):
        super().__init__()
        self._get_entries = get_entries
        self._submit_add = submit_add
        self._submit_remove = submit_remove
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        heading = QLabel("Whitelist Manager")
        heading.setObjectName("headingLabel")
        layout.addWidget(heading)

        sub = QLabel(
            "Devices listed below are allowed to connect. Others trigger "
            "lockdown. Add / remove requires the admin password."
        )
        sub.setObjectName("subheadingLabel")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("+ Add Device")
        self.add_btn.setObjectName("primary")
        self.add_btn.clicked.connect(self._on_add)
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.setObjectName("danger")
        self.remove_btn.clicked.connect(self._on_remove)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.remove_btn)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def refresh(self) -> None:
        self.list_widget.clear()
        for entry in self._get_entries():
            unlock = " [UNLOCK KEY]" if entry.get("can_unlock") else ""
            text = (f"{entry['label']}{unlock}\n"
                    f"  VID:PID = {entry['vendor_id']}:{entry['product_id']}    "
                    f"Serial = {entry['serial']}    "
                    f"Class = {entry['device_class']}\n"
                    f"  Added by {entry['added_by']} at {entry['added_at']}")
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, entry["id"])
            self.list_widget.addItem(item)

    def show_status(self, message: str, error: bool = False) -> None:
        """Briefly surface daemon feedback in a non-modal message box."""
        kind = QMessageBox.Critical if error else QMessageBox.Information
        QMessageBox(kind, "Whitelist", message, parent=self).exec_()

    def _prompt_password(self, prompt: str) -> str | None:
        pw, ok = QInputDialog.getText(
            self, "Admin Password Required", prompt, QLineEdit.Password,
        )
        if not ok or not pw:
            return None
        return pw

    def _on_add(self) -> None:
        dlg = AddDeviceDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        data = dlg.values()
        pw = self._prompt_password(
            f"Confirm adding '{data['label']}' — enter admin password:"
        )
        if pw is None:
            return
        self._submit_add(data, pw)

    def _on_remove(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        entry_id = item.data(Qt.UserRole)
        confirm = QMessageBox.question(
            self, "Confirm Remove",
            "Remove this device from the whitelist?\n"
            "It will be blocked next time it's plugged in.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        pw = self._prompt_password("Enter admin password to remove this device:")
        if pw is None:
            return
        self._submit_remove(entry_id, pw)


class AddDeviceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Device to Whitelist")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)

        self.label_input = QLineEdit()
        self.label_input.setPlaceholderText("e.g., Admin Backup Drive")
        self.vid_input = QLineEdit()
        self.vid_input.setPlaceholderText("e.g., 0951")
        self.pid_input = QLineEdit()
        self.pid_input.setPlaceholderText("e.g., 1666")
        self.serial_input = QLineEdit()
        self.serial_input.setPlaceholderText("e.g., 60A44C413FAEE2B129C9015A")
        self.class_input = QLineEdit()
        self.class_input.setPlaceholderText("e.g., MassStorage")
        self.unlock_check = QCheckBox("This USB can unlock the system from lockdown")

        layout.addRow("Label:", self.label_input)
        layout.addRow("Vendor ID (VID):", self.vid_input)
        layout.addRow("Product ID (PID):", self.pid_input)
        layout.addRow("Serial:", self.serial_input)
        layout.addRow("Device Class:", self.class_input)
        layout.addRow("", self.unlock_check)

        hint = QLabel(
            "Tip: plug in the USB and run <code>lsusb -v</code> in a "
            "terminal to find these values."
        )
        hint.setObjectName("subheadingLabel")
        hint.setWordWrap(True)
        layout.addRow(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict:
        return {
            "label": self.label_input.text().strip() or "Unlabeled",
            "vendor_id": self.vid_input.text().strip().lower(),
            "product_id": self.pid_input.text().strip().lower(),
            "serial": self.serial_input.text().strip(),
            "device_class": self.class_input.text().strip() or "Unknown",
            "can_unlock": self.unlock_check.isChecked(),
        }
