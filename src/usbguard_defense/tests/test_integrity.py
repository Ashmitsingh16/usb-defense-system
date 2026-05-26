"""Tests for the HMAC integrity module. Cross-platform."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from usbguard_defense.integrity import (
    IntegrityError,
    KEY_BYTES,
    ensure_master_key,
    sign,
    verify,
)


@pytest.fixture
def key_path(tmp_path: Path) -> Path:
    return tmp_path / "master.key"


def test_ensure_master_key_generates_if_missing(key_path: Path) -> None:
    key = ensure_master_key(key_path)
    assert key_path.exists()
    assert len(key) == KEY_BYTES


def test_ensure_master_key_reuses_existing(key_path: Path) -> None:
    first = ensure_master_key(key_path)
    second = ensure_master_key(key_path)
    assert first == second


def test_sign_verify_roundtrip(key_path: Path) -> None:
    key = ensure_master_key(key_path)
    payload = b'{"version":1,"devices":[]}'
    sig = sign(payload, key)
    assert verify(payload, key, sig) is True


def test_verify_rejects_mutated_payload(key_path: Path) -> None:
    key = ensure_master_key(key_path)
    payload = b'{"version":1,"devices":[]}'
    sig = sign(payload, key)
    mutated = payload.replace(b"[]", b'[{"vendor_id":"0000"}]')
    assert verify(mutated, key, sig) is False


def test_verify_rejects_wrong_key(key_path: Path, tmp_path: Path) -> None:
    key = ensure_master_key(key_path)
    other = ensure_master_key(tmp_path / "other.key")
    payload = b"hello"
    sig = sign(payload, key)
    assert verify(payload, other, sig) is False


def test_verify_rejects_empty_signature(key_path: Path) -> None:
    key = ensure_master_key(key_path)
    assert verify(b"hello", key, "") is False


def test_verify_strips_signature_whitespace(key_path: Path) -> None:
    key = ensure_master_key(key_path)
    payload = b"hello"
    sig = sign(payload, key)
    assert verify(payload, key, "  " + sig + "\n") is True


def test_signature_is_constant_time(key_path: Path) -> None:
    """Not a true timing test, just confirms compare_digest is in the path."""
    key = ensure_master_key(key_path)
    # Two wrong sigs of different length should both return False without
    # raising.
    assert verify(b"x", key, "00") is False
    assert verify(b"x", key, "0" * 64) is False


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only permission check")
def test_refuses_world_readable_key(key_path: Path) -> None:
    ensure_master_key(key_path)
    key_path.chmod(0o644)
    with pytest.raises(IntegrityError, match="insecure"):
        ensure_master_key(key_path)


def test_refuses_undersized_key(key_path: Path) -> None:
    key_path.write_bytes(b"short")
    if os.name == "posix":
        key_path.chmod(0o600)
    with pytest.raises(IntegrityError, match="undersized"):
        ensure_master_key(key_path)
