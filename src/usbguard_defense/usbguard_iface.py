"""Wrapper around the `usbguard` CLI for blocking/allowing devices.

Using subprocess + CLI rather than D-Bus to keep deps minimal.
USBGuard is the existing kernel-level enforcement layer; we use it for the
actual block/allow, then layer our own policy/UI on top.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Optional


log = logging.getLogger(__name__)


@dataclass
class USBGuardDevice:
    device_id: int  # usbguard's internal ID
    target: str     # "allow", "block", "reject"
    name: str
    vendor_id: str
    product_id: str
    serial: str


class USBGuard:
    @staticmethod
    def list_devices() -> list[USBGuardDevice]:
        """Returns all currently visible USB devices known to USBGuard."""
        result = subprocess.run(
            ["usbguard", "list-devices"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            log.error("usbguard list-devices failed: %s", result.stderr)
            return []
        devices = []
        for line in result.stdout.strip().splitlines():
            # Format: "12: allow id 0951:1666 serial \"60A44C413\" name \"DataTraveler\" ..."
            parsed = USBGuard._parse_device_line(line)
            if parsed:
                devices.append(parsed)
        return devices

    @staticmethod
    def _parse_device_line(line: str) -> Optional[USBGuardDevice]:
        try:
            colon_idx = line.index(":")
            device_id = int(line[:colon_idx].strip())
            rest = line[colon_idx + 1:].strip()
            target = rest.split(" ", 1)[0]
            vid, pid, serial, name = "", "", "", ""
            tokens = rest.split()
            for i, tok in enumerate(tokens):
                if tok == "id" and i + 1 < len(tokens):
                    parts = tokens[i + 1].split(":")
                    if len(parts) == 2:
                        vid, pid = parts[0].lower(), parts[1].lower()
                if tok == "serial" and i + 1 < len(tokens):
                    serial = tokens[i + 1].strip('"')
                if tok == "name" and i + 1 < len(tokens):
                    # name may be multi-word, take everything between quotes
                    name_start = rest.index('name "') + len('name "')
                    name_end = rest.index('"', name_start)
                    name = rest[name_start:name_end]
            return USBGuardDevice(device_id, target, name, vid, pid, serial)
        except (ValueError, IndexError):
            return None

    @staticmethod
    def block_device(device_id: int) -> bool:
        return USBGuard._set_target(device_id, "block")

    @staticmethod
    def allow_device(device_id: int) -> bool:
        return USBGuard._set_target(device_id, "allow")

    @staticmethod
    def reject_device(device_id: int) -> bool:
        return USBGuard._set_target(device_id, "reject")

    @staticmethod
    def _set_target(device_id: int, target: str) -> bool:
        result = subprocess.run(
            ["usbguard", "apply-device-policy", str(device_id), target],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            log.error("usbguard apply-device-policy failed: %s", result.stderr)
            return False
        return True

    @staticmethod
    def find_by_fingerprint(vendor_id: str, product_id: str, serial: str) -> Optional[USBGuardDevice]:
        vendor_id = vendor_id.lower()
        product_id = product_id.lower()
        for d in USBGuard.list_devices():
            if d.vendor_id == vendor_id and d.product_id == product_id and d.serial == serial:
                return d
        return None
