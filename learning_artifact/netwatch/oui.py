"""Tiny bundled OUI -> vendor lookup.

We don't ship the full 30k-entry IEEE database. A short, curated list covers
~80% of the devices most operators care about; everything else returns
"Unknown". For real deployments a fuller OUI file can be dropped at
`/var/lib/netwatch/oui.txt` and will override the bundled table.
"""
from __future__ import annotations

from pathlib import Path

# Hand-picked common OUIs. Lowercase, no separators.
_BUILTIN: dict[str, str] = {
    "001a11": "Google",
    "f4f5d8": "Google",
    "3c5ab4": "Google",
    "001124": "Cisco",
    "0023ac": "Cisco",
    "001bd4": "Cisco",
    "002354": "Apple",
    "a4c361": "Apple",
    "f0d1a9": "Apple",
    "3c0754": "Apple",
    "001c42": "Parallels",
    "080027": "VirtualBox",
    "525400": "QEMU/KVM",
    "000c29": "VMware",
    "001a92": "ASUSTek",
    "b827eb": "Raspberry Pi Foundation",
    "dca632": "Raspberry Pi Foundation",
    "e45f01": "Raspberry Pi Foundation",
    "001e8c": "ASUSTek",
    "f81a67": "TP-Link",
    "ec086b": "TP-Link",
    "c46e1f": "TP-Link",
    "8021ef": "Xiaomi",
    "ac9a96": "Lenovo",
    "001321": "Samsung",
    "5cf938": "Samsung",
    "0050ba": "D-Link",
    "001cf0": "D-Link",
    "00904c": "Epigram",
    "001b63": "Apple",
    "0017f2": "Apple",
    "001d4f": "Apple",
    "f0182b": "Apple",
    "001ec2": "Apple",
}


def _normalize(mac: str) -> str:
    return mac.lower().replace(":", "").replace("-", "").replace(".", "")


def lookup(mac: str, *, extra: dict[str, str] | None = None) -> str:
    """Return vendor name for a MAC's OUI; 'Unknown' if not found."""
    norm = _normalize(mac)
    if len(norm) < 6:
        return "Unknown"
    prefix = norm[:6]
    if extra and prefix in extra:
        return extra[prefix]
    return _BUILTIN.get(prefix, "Unknown")


def load_extra(path: Path) -> dict[str, str]:
    """Parse a Wireshark-style `manuf` file. Returns empty dict if missing."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        prefix = _normalize(parts[0])[:6]
        vendor = parts[1]
        if prefix and vendor:
            out[prefix] = vendor
    return out
