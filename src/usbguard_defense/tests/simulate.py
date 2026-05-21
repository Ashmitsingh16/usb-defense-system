"""USB event simulator — sends synthetic events to the daemon over IPC.

Useful for exercising every demo path without real hardware. Run while the
daemon is up:

    python -m usbguard_defense.tests.simulate <scenario>

Demo coverage:
    Demo 1 (authorized USB allowed):        authorized_key  |  authorized_normal
    Demo 2 (unauthorized USB → lockdown):   unauthorized    |  lockdown
    Demo 3 (asymmetric unlock):             1) lockdown
                                            2) authorized_normal  (stays locked)
                                            3) authorized_key     (clears lockdown)
    Demo 5 (BadUSB HID-injection):          badusb          (HID-Keyboard class)
"""

from __future__ import annotations

import json
import socket
import sys
import time

from ..config import IPC_SOCKET


# Shared device dicts so the scenarios stay readable.
_EVIL_STORAGE = {
    "vendor_id": "1234",
    "product_id": "abcd",
    "serial": "FAKE-SERIAL-EVIL",
    "fingerprint": "1234:abcd:FAKE-SERIAL-EVIL",
    "manufacturer": "Suspicious Inc",
    "product": "Sketchy Stick",
    "device_class": "MassStorage",
    "usb_version": "3.0",
    "capacity_bytes": 32 * 1024 ** 3,
    "devnode": "/dev/sdz",
}

_BADUSB_HID = {
    "vendor_id": "03eb",
    "product_id": "2402",
    "serial": "HAK5-DUCKY-SIM",
    "fingerprint": "03eb:2402:HAK5-DUCKY-SIM",
    "manufacturer": "Hak5",
    "product": "USB Rubber Ducky (simulated)",
    "device_class": "HID-Keyboard",
    "usb_version": "2.0",
    "devnode": "/dev/input/eventX",
}

_ADMIN_KEY = {
    "vendor_id": "0951",
    "product_id": "1666",
    "serial": "60A44C413FAEE2B129C9015A",
    "fingerprint": "0951:1666:60A44C413FAEE2B129C9015A",
    "manufacturer": "Kingston",
    "product": "DataTraveler 3.0",
    "device_class": "MassStorage",
    "usb_version": "3.0",
}

_REGULAR_AUTH = {
    "vendor_id": "0781",
    "product_id": "5567",
    "serial": "4C530001120628116341",
    "fingerprint": "0781:5567:4C530001120628116341",
    "manufacturer": "SanDisk",
    "product": "Cruzer Blade",
    "device_class": "MassStorage",
    "usb_version": "2.0",
}


SCENARIOS = {
    "unauthorized": {
        "type": "unauthorized_insert",
        "device": _EVIL_STORAGE,
    },
    "lockdown": {
        "type": "lockdown_enter",
        "offender": _EVIL_STORAGE,
    },
    "unlock": {
        "type": "lockdown_clear",
        "reason": "test simulation",
    },
    # Demo 1 / Demo 3 step 3 — authorized USB that is ALSO a master key.
    "authorized_key": {
        "type": "authorized_insert",
        "device": _ADMIN_KEY,
        "label": "Admin Backup Drive",
        "can_unlock": True,
    },
    # Backwards-compat alias for older runbook commands.
    "authorized": {
        "type": "authorized_insert",
        "device": _ADMIN_KEY,
        "label": "Admin Backup Drive",
        "can_unlock": True,
    },
    # Demo 3 step 2 — authorized for data, but NOT trusted to unlock the system.
    # When fired while locked, the daemon allows the device through but leaves
    # the lockdown overlay in place. Proves the asymmetric-unlock design.
    "authorized_normal": {
        "type": "authorized_insert",
        "device": _REGULAR_AUTH,
        "label": "Field Engineer Data Drive",
        "can_unlock": False,
    },
    # Demo 5 — BadUSB / Rubber Ducky simulation. The device claims to be a
    # keyboard (HID-Keyboard) but its VID:PID:Serial isn't whitelisted, so the
    # daemon treats it as unauthorized and the system enters lockdown before
    # any HID payload can run.
    "badusb": {
        "type": "unauthorized_insert",
        "device": _BADUSB_HID,
    },
    "badusb_lockdown": {
        "type": "lockdown_enter",
        "offender": _BADUSB_HID,
    },
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in SCENARIOS:
        print("Usage: simulate.py <scenario>")
        print("Scenarios:", ", ".join(SCENARIOS.keys()))
        return 1

    scenario = sys.argv[1]
    payload = SCENARIOS[scenario]

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(IPC_SOCKET))
    except (FileNotFoundError, ConnectionRefusedError):
        print(f"Daemon socket {IPC_SOCKET} not found — is the daemon running?")
        return 2

    # Wrap as a daemon command so the daemon broadcasts the payload to every
    # connected UI client (and triggers real lockdown / unlock state changes
    # for lockdown_enter / lockdown_clear).
    envelope = {"cmd": "simulate_event", "event": payload}
    sock.sendall((json.dumps(envelope) + "\n").encode("utf-8"))
    print(f"Sent: {scenario}")
    time.sleep(0.2)
    sock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
