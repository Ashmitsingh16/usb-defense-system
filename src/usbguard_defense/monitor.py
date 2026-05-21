"""USB event monitoring via pyudev. Runs in its own thread."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable, Optional

import pyudev


log = logging.getLogger(__name__)


# USB device class codes (bDeviceClass / bInterfaceClass)
DEVICE_CLASS_NAMES = {
    "00": "InterfaceDefined",
    "01": "Audio",
    "02": "CDC",
    "03": "HID",
    "05": "Physical",
    "06": "Image",
    "07": "Printer",
    "08": "MassStorage",
    "09": "Hub",
    "0a": "CDCData",
    "0b": "SmartCard",
    "0d": "ContentSecurity",
    "0e": "Video",
    "0f": "PersonalHealthcare",
    "10": "AudioVideo",
    "11": "Billboard",
    "dc": "Diagnostic",
    "e0": "WirelessController",
    "ef": "Miscellaneous",
    "fe": "ApplicationSpecific",
    "ff": "VendorSpecific",
}


@dataclass
class USBEvent:
    action: str  # "add" or "remove"
    vendor_id: str
    product_id: str
    serial: str
    device_class: str
    device_class_name: str
    usb_version: str
    manufacturer: str
    product: str
    devnode: Optional[str]  # /dev/sdb etc., None if not block device
    capacity_bytes: Optional[int]
    sysfs_path: str

    def fingerprint(self) -> str:
        return f"{self.vendor_id}:{self.product_id}:{self.serial}"

    def short_desc(self) -> str:
        return f"{self.manufacturer} {self.product} ({self.fingerprint()})"


class USBMonitor:
    """Watches udev for USB device add/remove events.

    Calls user-supplied callback on each event. Filters to USB subsystem only.
    """

    def __init__(self, on_event: Callable[[USBEvent], None]):
        self.on_event = on_event
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._context = pyudev.Context()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="USBMonitor")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        monitor = pyudev.Monitor.from_netlink(self._context)
        monitor.filter_by(subsystem="usb")
        for device in iter(monitor.poll, None):
            if self._stop.is_set():
                break
            if device.action not in ("add", "remove"):
                continue
            # We only care about whole devices, not individual interfaces.
            if device.get("DEVTYPE") != "usb_device":
                continue
            try:
                event = self._build_event(device)
                self.on_event(event)
            except Exception:
                log.exception("Failed handling udev event for %s", device.sys_path)

    @staticmethod
    def _build_event(device) -> USBEvent:
        vid = (device.get("ID_VENDOR_ID") or "").lower()
        pid = (device.get("ID_MODEL_ID") or "").lower()
        serial = device.get("ID_SERIAL_SHORT") or device.get("ID_SERIAL") or ""
        device_class_hex = (device.attributes.get("bDeviceClass") or b"").decode(errors="ignore").lower()
        # bDeviceClass=00 means "look at interface descriptors" — fall back to the
        # first interface's class so MassStorage/HID/etc. are reported correctly.
        if device_class_hex in ("", "00"):
            ifaces = device.get("ID_USB_INTERFACES") or ""
            # Format is ":CCSSPP:CCSSPP:" where CC is interface class (hex).
            for part in ifaces.strip(":").split(":"):
                if len(part) >= 2:
                    device_class_hex = part[:2].lower()
                    break
        usb_version = (device.attributes.get("version") or b"").decode(errors="ignore").strip()
        manufacturer = device.get("ID_VENDOR") or device.get("ID_VENDOR_FROM_DATABASE") or "Unknown"
        product = device.get("ID_MODEL") or device.get("ID_MODEL_FROM_DATABASE") or "Unknown"
        # Find associated block device (for mass storage)
        devnode = None
        capacity_bytes = None
        try:
            for child in device.children:
                if child.subsystem == "block" and child.device_type == "disk":
                    devnode = child.device_node
                    size_str = child.attributes.get("size")
                    if size_str:
                        # Linux block device size is in 512-byte sectors.
                        capacity_bytes = int(size_str) * 512
                    break
        except Exception:
            log.debug("No block device child for %s", device.sys_path)
        return USBEvent(
            action=device.action,
            vendor_id=vid,
            product_id=pid,
            serial=serial,
            device_class=device_class_hex,
            device_class_name=DEVICE_CLASS_NAMES.get(device_class_hex, "Unknown"),
            usb_version=usb_version,
            manufacturer=manufacturer.replace("_", " "),
            product=product.replace("_", " "),
            devnode=devnode,
            capacity_bytes=capacity_bytes,
            sysfs_path=device.sys_path,
        )
