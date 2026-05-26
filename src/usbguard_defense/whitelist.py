"""Whitelist data model and matching logic.

v0.2.0 — load/save verify and rewrite an HMAC-SHA256 sidecar at
whitelist.sig when a master key is supplied. If integrity verification
fails the whitelist is treated as EMPTY (fail closed) and
`integrity_failed` is set; the daemon escalates that to a tamper event.
Code paths that construct `Whitelist()` without a key (notably existing
unit tests) keep working with no integrity check.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import WHITELIST_PATH, WHITELIST_SIG_PATH
from .integrity import sign, verify


log = logging.getLogger(__name__)


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

    def __init__(self, path: Path = WHITELIST_PATH,
                 master_key: Optional[bytes] = None,
                 sig_path: Optional[Path] = None) -> None:
        self.path = path
        self.master_key = master_key
        self.sig_path = sig_path if sig_path is not None else (
            WHITELIST_SIG_PATH if path == WHITELIST_PATH
            else path.with_suffix(path.suffix + ".sig")
        )
        self.entries: list[WhitelistEntry] = []
        self.integrity_failed: bool = False
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self.entries = []
            self.integrity_failed = False
            return
        raw = self.path.read_bytes()
        if self.master_key is not None:
            if not self.sig_path.exists():
                log.error(
                    "Whitelist signature %s missing — refusing to load entries",
                    self.sig_path,
                )
                self.entries = []
                self.integrity_failed = True
                return
            try:
                signature = self.sig_path.read_text().strip()
            except OSError as exc:
                log.error("Cannot read whitelist signature: %s", exc)
                self.entries = []
                self.integrity_failed = True
                return
            if not verify(raw, self.master_key, signature):
                log.error(
                    "Whitelist signature INVALID — possible tamper. "
                    "Treating whitelist as empty (fail closed)."
                )
                self.entries = []
                self.integrity_failed = True
                return
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            log.error("Whitelist JSON corrupt: %s", exc)
            self.entries = []
            self.integrity_failed = True
            return
        self.entries = [WhitelistEntry(**e) for e in data.get("devices", [])]
        self.integrity_failed = False

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"version": 1, "devices": [asdict(e) for e in self.entries]},
            indent=2,
        ).encode("utf-8")
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except PermissionError:
            pass
        if self.master_key is not None:
            sig = sign(payload, self.master_key)
            tmp_sig = self.sig_path.with_suffix(self.sig_path.suffix + ".tmp")
            self.sig_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_sig.write_text(sig)
            os.replace(tmp_sig, self.sig_path)
            try:
                os.chmod(self.sig_path, 0o600)
            except PermissionError:
                pass
        self.integrity_failed = False

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
