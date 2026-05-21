"""Unit tests for the USBGuard CLI output parser.

These do NOT call the real `usbguard` binary; they test the line parser in
isolation. The parser is the most fragile bit of the integration so it gets
explicit fixture coverage for the various output shapes we see in the wild.
"""

from __future__ import annotations

from usbguard_defense.usbguard_iface import USBGuard


def test_parse_typical_allow_line():
    line = ('12: allow id 0951:1666 serial "60A44C413FAEE2B129C9015A" '
            'name "DataTraveler 3.0" hash "abc==" parent-hash "def==" '
            'via-port "2-1" with-interface { 08:06:50 } '
            'with-connect-type "hardwired"')
    d = USBGuard._parse_device_line(line)
    assert d is not None
    assert d.device_id == 12
    assert d.target == "allow"
    assert d.vendor_id == "0951"
    assert d.product_id == "1666"
    assert d.serial == "60A44C413FAEE2B129C9015A"
    assert d.name == "DataTraveler 3.0"


def test_parse_block_line():
    line = ('7: block id dead:beef serial "EVIL-001" name "Sketchy" '
            'hash "x==" via-port "1-1" with-interface { 03:01:01 }')
    d = USBGuard._parse_device_line(line)
    assert d is not None
    assert d.device_id == 7
    assert d.target == "block"
    assert d.vendor_id == "dead"
    assert d.product_id == "beef"


def test_parse_lowercases_vid_pid():
    line = '1: allow id 0951:ABCD serial "X" name "Y"'
    d = USBGuard._parse_device_line(line)
    assert d is not None
    assert d.vendor_id == "0951"
    assert d.product_id == "abcd"


def test_parse_garbage_returns_none():
    assert USBGuard._parse_device_line("complete garbage line") is None


def test_parse_empty_string_returns_none():
    assert USBGuard._parse_device_line("") is None


def test_parse_missing_id_field_returns_none_or_empty():
    # Without `id VID:PID`, our parser leaves vid/pid empty but still returns
    # a record. This is acceptable — the matcher will fail to find a match
    # and the device won't be processed.
    line = '1: allow name "No-ID-Device"'
    d = USBGuard._parse_device_line(line)
    if d is not None:
        assert d.vendor_id == ""
        assert d.product_id == ""
