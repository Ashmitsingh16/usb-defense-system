"""Event log viewer."""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)


class EventLogWidget(QWidget):
    HEADERS = ["Time", "Type", "Device", "VID:PID", "Serial", "Class", "Fingerprint"]

    def __init__(self, get_events: Callable[[], list[dict]]):
        super().__init__()
        self._get_events = get_events
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        heading = QLabel("Event Log")
        heading.setObjectName("headingLabel")
        layout.addWidget(heading)

        sub = QLabel("All USB events recorded by the daemon.")
        sub.setObjectName("subheadingLabel")
        layout.addWidget(sub)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        self.export_btn = QPushButton("Export CSV…")
        self.export_btn.clicked.connect(self._export_csv)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.export_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def refresh(self) -> None:
        events = self._get_events()
        self.table.setRowCount(len(events))
        for row, ev in enumerate(events):
            cells = [
                ev.get("ts", ""),
                ev.get("type", ""),
                f"{ev.get('manufacturer','')} {ev.get('product','')}".strip(),
                f"{ev.get('vendor_id','')}:{ev.get('product_id','')}",
                ev.get("serial", ""),
                ev.get("device_class", ""),
                ev.get("fingerprint", ""),
            ]
            for col, text in enumerate(cells):
                self.table.setItem(row, col, QTableWidgetItem(str(text)))
        self.table.resizeColumnsToContents()

    def _export_csv(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        import csv
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "events.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(self.HEADERS)
            for row in range(self.table.rowCount()):
                writer.writerow([
                    self.table.item(row, col).text() if self.table.item(row, col) else ""
                    for col in range(self.table.columnCount())
                ])
