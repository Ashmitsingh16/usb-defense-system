"""Baseline of known MACs.

During the first `learning_seconds` after startup every observation is silently
added to the baseline. After that, an observation of an unknown MAC is an
alert. The baseline is persisted as JSON so a daemon restart doesn't trigger
spurious alerts.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from netwatch import oui


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_mac(mac: str) -> str:
    """Canonical MAC form: lowercase, colon-separated."""
    cleaned = mac.lower().replace("-", ":").replace(".", ":")
    parts = cleaned.split(":")
    if len(parts) == 1 and len(cleaned) == 12:
        parts = [cleaned[i : i + 2] for i in range(0, 12, 2)]
    if len(parts) != 6:
        raise ValueError(f"invalid MAC: {mac!r}")
    return ":".join(p.zfill(2) for p in parts)


@dataclass
class Device:
    mac: str
    vendor: str
    first_seen: str
    last_seen: str
    last_ip: str | None = None
    hostname: str | None = None
    iface: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


@dataclass
class Baseline:
    """Thread-safe device registry persisted to JSON."""

    path: Path
    learning_seconds: int = 90
    started_at: float = field(default_factory=time.monotonic)
    devices: dict[str, Device] = field(default_factory=dict)
    whitelist: set[str] = field(default_factory=set)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # ------------------------------------------------------------------ state
    def is_learning(self) -> bool:
        with self._lock:
            return (time.monotonic() - self.started_at) < self.learning_seconds

    def is_known(self, mac: str) -> bool:
        mac = normalize_mac(mac)
        with self._lock:
            return mac in self.devices or mac in self.whitelist

    def add_whitelist(self, mac: str) -> None:
        mac = normalize_mac(mac)
        with self._lock:
            self.whitelist.add(mac)

    def remove_whitelist(self, mac: str) -> bool:
        mac = normalize_mac(mac)
        with self._lock:
            if mac in self.whitelist:
                self.whitelist.discard(mac)
                return True
            return False

    def reset_learning(self) -> None:
        with self._lock:
            self.started_at = time.monotonic()
            self.devices.clear()

    # ---------------------------------------------------------------- observe
    def observe(
        self,
        mac: str,
        *,
        ip: str | None = None,
        hostname: str | None = None,
        iface: str | None = None,
    ) -> tuple[Device, bool]:
        """Record an observation.

        Returns (device, is_new). `is_new=True` means this MAC was not in the
        baseline before AND learning mode is over — i.e. caller should alert.
        """
        mac = normalize_mac(mac)
        with self._lock:
            now = _now_iso()
            existing = self.devices.get(mac)
            if existing is not None:
                existing.last_seen = now
                if ip:
                    existing.last_ip = ip
                if hostname:
                    existing.hostname = hostname
                if iface:
                    existing.iface = iface
                return existing, False

            device = Device(
                mac=mac,
                vendor=oui.lookup(mac),
                first_seen=now,
                last_seen=now,
                last_ip=ip,
                hostname=hostname,
                iface=iface,
            )
            self.devices[mac] = device
            is_intruder = (not self.is_learning()) and (mac not in self.whitelist)
            return device, is_intruder

    # --------------------------------------------------------------- persist
    def save(self) -> None:
        with self._lock:
            payload = {
                "saved_at": _now_iso(),
                "learning_seconds": self.learning_seconds,
                "whitelist": sorted(self.whitelist),
                "devices": {m: d.to_dict() for m, d in self.devices.items()},
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + f".tmp.{secrets.token_hex(4)}")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)

    @classmethod
    def load(cls, path: Path, *, learning_seconds: int = 90) -> "Baseline":
        if not path.exists():
            return cls(path=path, learning_seconds=learning_seconds)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls(path=path, learning_seconds=learning_seconds)

        b = cls(
            path=path,
            learning_seconds=int(raw.get("learning_seconds", learning_seconds)),
            # Loaded baselines skip learning — we already know these devices.
            started_at=time.monotonic() - max(learning_seconds, 1) - 1,
        )
        b.whitelist = {normalize_mac(m) for m in raw.get("whitelist", [])}
        for mac, d in (raw.get("devices") or {}).items():
            try:
                b.devices[normalize_mac(mac)] = Device(
                    mac=normalize_mac(mac),
                    vendor=str(d.get("vendor", "Unknown")),
                    first_seen=str(d.get("first_seen", _now_iso())),
                    last_seen=str(d.get("last_seen", _now_iso())),
                    last_ip=d.get("last_ip"),
                    hostname=d.get("hostname"),
                    iface=d.get("iface"),
                )
            except ValueError:
                continue
        return b
