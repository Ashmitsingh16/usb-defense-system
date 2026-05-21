"""Whitelist data model and matching logic."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import WHITELIST_PATH


@dataclass
class WhitelistEntry:
    id: str
    label: str
    vendor_id: str
    product_id: str
    serial: str
    device_class: str
    added_by: str
    added_at: str
    can_unlock: bool = False

    @staticmethod
    def new(label: str, vendor_id: str, product_id: str, serial: str,
            device_class: str, added_by: str, can_unlock: bool = False) -> "WhitelistEntry":
        return WhitelistEntry(
            id=str(uuid.uuid4()),
            label=label,
            vendor_id=vendor_id.lower(),
            product_id=product_id.lower(),
            serial=serial,
            device_class=device_class,
            added_by=added_by,
            added_at=datetime.now(timezone.utc).isoformat(),
            can_unlock=can_unlock,
        )


class Whitelist:
    """Read/write authorized device list. Thread-safe via atomic file replace."""

    def __init__(self, path: Path = WHITELIST_PATH):
        self.path = path
        self.entries: list[WhitelistEntry] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self.entries = []
            return
        with self.path.open("r") as fh:
            data = json.load(fh)
        self.entries = [WhitelistEntry(**e) for e in data.get("devices", [])]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with tmp.open("w") as fh:
            json.dump(
                {"version": 1, "devices": [asdict(e) for e in self.entries]},
                fh, indent=2,
            )
        os.replace(tmp, self.path)
        # Restrict permissions: root only
        try:
            os.chmod(self.path, 0o600)
        except PermissionError:
            pass

    def match(self, vendor_id: str, product_id: str, serial: str) -> Optional[WhitelistEntry]:
        """Return the matching entry or None."""
        vendor_id = vendor_id.lower()
        product_id = product_id.lower()
        for entry in self.entries:
            if (entry.vendor_id == vendor_id
                    and entry.product_id == product_id
                    and entry.serial == serial):
                return entry
        return None

    def can_unlock(self, vendor_id: str, product_id: str, serial: str) -> bool:
        entry = self.match(vendor_id, product_id, serial)
        return entry is not None and entry.can_unlock

    def add(self, entry: WhitelistEntry) -> None:
        # Replace if exists with same VID:PID:Serial
        self.entries = [e for e in self.entries
                        if not (e.vendor_id == entry.vendor_id
                                and e.product_id == entry.product_id
                                and e.serial == entry.serial)]
        self.entries.append(entry)
        self.save()

    def remove(self, entry_id: str) -> bool:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.id != entry_id]
        if len(self.entries) < before:
            self.save()
            return True
        return False
