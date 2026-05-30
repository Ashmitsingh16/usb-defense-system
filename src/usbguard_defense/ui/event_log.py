"""Event log viewer.

v0.3.0: timestamps are now rendered in the operator's local time zone
(YYYY-MM-DD HH:MM:SS) instead of the raw UTC ISO string the daemon
writes to disk. An extra ``Detail`` column shows the intrusion-attempt
reason for ``INTRUSION_ATTEMPT`` rows so the operator can read the
full story without opening events.log by hand.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from PyQt5.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)


class EventLogWidget(QWidget):
    HEADERS = [
        "Time (local)", "Type", "Device", "VID:PID", "Serial",
        "Class", "Detail", "Fingerprint",
    ]

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

        sub = QLabel(
            "All USB events and intrusion attempts recorded by the daemon. "
            "Times are shown in your local time zone."
        )
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
                format_local_time(ev.get("ts", "")),
                ev.get("type", ""),
                f"{ev.get('manufacturer','')} {ev.get('product','')}".strip(),
                f"{ev.get('vendor_id','')}:{ev.get('product_id','')}",
                ev.get("serial", ""),
                ev.get("device_class", ""),
                _detail_text(ev),
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


def format_local_time(iso_ts: str) -> str:
    """Render an ISO-8601 UTC timestamp as ``YYYY-MM-DD HH:MM:SS`` local.

    Falls back to the raw value if it isn't parseable so that an
    unexpectedly-formatted row still shows *something* rather than a
    blank cell.
    """
    if not iso_ts:
        return ""
    try:
        parsed = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return iso_ts
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _detail_text(ev: dict) -> str:
    etype = ev.get("type", "")
    if etype == "INTRUSION_ATTEMPT":
        kind = ev.get("kind", "")
        detail = ev.get("detail", "")
        return f"{kind}: {detail}" if kind else detail
    if etype == "UNLOCK_AUTH_FAILURE":
        return f"method={ev.get('method', '?')}"
    if etype == "UNLOCK_SUCCESS":
        return f"method={ev.get('method', '?')}"
    if etype == "WHITELIST_ADD":
        return f"label={ev.get('label', '')}"
    if etype == "WHITELIST_REMOVE":
        return f"entry_id={ev.get('entry_id', '')}"
    if etype == "WHITELIST_TAMPER":
        return f"detected_at={ev.get('detected_at', '')}"
    if etype == "AUTH_FAILURE":
        return f"op={ev.get('op', '')}"
    return ""
