"""Scenario-shape tests for the offline USB event simulator.

The simulator is what drives Demo 3 (asymmetric unlock) and Demo 5 (BadUSB) in
the viva without real hardware, so the scenario dict is part of the report's
evidence chain — we lock its shape down here.
"""

from __future__ import annotations

from usbguard_defense.tests.simulate import SCENARIOS


REQUIRED_SCENARIOS = {
    "unauthorized", "lockdown", "unlock",
    "authorized", "authorized_key", "authorized_normal",
    "badusb", "badusb_lockdown",
}


def test_every_required_scenario_is_present():
    assert REQUIRED_SCENARIOS.issubset(SCENARIOS.keys())


def test_every_scenario_has_a_type():
    for name, payload in SCENARIOS.items():
        assert "type" in payload, f"scenario {name!r} missing 'type'"


def test_authorized_key_is_an_unlock_key():
    s = SCENARIOS["authorized_key"]
    assert s["type"] == "authorized_insert"
    assert s["can_unlock"] is True


def test_authorized_normal_is_data_only():
    """Demo 3 hinges on this device being authorized but unable to unlock."""
    s = SCENARIOS["authorized_normal"]
    assert s["type"] == "authorized_insert"
    assert s["can_unlock"] is False


def test_badusb_claims_hid_keyboard_class():
    """BadUSB scenarios must look like a keyboard, otherwise the demo is meaningless."""
    s = SCENARIOS["badusb"]
    assert s["type"] == "unauthorized_insert"
    assert s["device"]["device_class"] == "HID-Keyboard"


def test_lockdown_offender_has_fingerprint():
    s = SCENARIOS["lockdown"]
    assert s["type"] == "lockdown_enter"
    assert "fingerprint" in s["offender"]
