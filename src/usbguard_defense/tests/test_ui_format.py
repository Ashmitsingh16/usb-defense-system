"""Tests for the UI-side timestamp formatter and intrusion-row helper.

PyQt5 is an install-time dependency on the target box but isn't always
present in the dev/CI venv. Skip cleanly if it's missing — the desktop
install will exercise this code path at runtime regardless.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("PyQt5")

from usbguard_defense.ui.event_log import _detail_text, format_local_time
from usbguard_defense.ui.lockdown import _iso_to_local_full, _iso_to_local_hms


def test_format_local_time_parses_iso_with_offset() -> None:
    iso = "2026-05-30T14:30:45+00:00"
    out = format_local_time(iso)
    # We don't assert the local string itself (it depends on $TZ), but
    # it must be the YYYY-MM-DD HH:MM:SS shape and not the raw ISO.
    assert len(out) == 19
    assert out[4] == "-" and out[7] == "-" and out[10] == " "
    assert out[13] == ":" and out[16] == ":"


def test_format_local_time_handles_z_suffix() -> None:
    out = format_local_time("2026-05-30T14:30:45Z")
    assert len(out) == 19


def test_format_local_time_passes_through_unparseable() -> None:
    # If the daemon ever logs something we can't parse we want the raw
    # value, not a crash and not a blank.
    assert format_local_time("not a timestamp") == "not a timestamp"


def test_format_local_time_handles_empty() -> None:
    assert format_local_time("") == ""


def test_iso_to_local_hms_returns_eight_chars() -> None:
    iso = datetime.now(timezone.utc).isoformat()
    out = _iso_to_local_hms(iso)
    assert len(out) == 8
    assert out[2] == ":" and out[5] == ":"


def test_iso_to_local_hms_fallback_on_bad_input() -> None:
    assert _iso_to_local_hms("garbage") == "garbage"
    assert _iso_to_local_hms("") == "??:??:??"


def test_iso_to_local_full_empty_on_bad_input() -> None:
    assert _iso_to_local_full("garbage") == ""
    assert _iso_to_local_full("") == ""


def test_detail_text_renders_intrusion_attempt() -> None:
    row = {
        "type": "INTRUSION_ATTEMPT",
        "kind": "WRONG_PASSWORD",
        "detail": "Failed admin-password unlock attempt",
    }
    out = _detail_text(row)
    assert "WRONG_PASSWORD" in out
    assert "Failed admin-password unlock attempt" in out


def test_detail_text_renders_unlock_auth_failure() -> None:
    out = _detail_text({"type": "UNLOCK_AUTH_FAILURE", "method": "password"})
    assert out == "method=password"


def test_detail_text_empty_for_unknown_type() -> None:
    assert _detail_text({"type": "REMOVE"}) == ""
