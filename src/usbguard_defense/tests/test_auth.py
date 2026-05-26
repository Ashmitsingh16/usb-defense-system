"""Tests for the admin password module. Cross-platform (run on Windows too)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from usbguard_defense.auth import (
    MIN_PASSWORD_LEN,
    AuthError,
    is_admin_password_set,
    set_admin_password,
    verify_admin_password,
)


@pytest.fixture
def hash_path(tmp_path: Path) -> Path:
    return tmp_path / "admin.hash"


def test_not_set_initially(hash_path: Path) -> None:
    assert is_admin_password_set(hash_path) is False


def test_set_then_marked_set(hash_path: Path) -> None:
    set_admin_password("hunter2x", hash_path)
    assert is_admin_password_set(hash_path) is True


def test_verify_correct_password(hash_path: Path) -> None:
    set_admin_password("correctpw", hash_path)
    assert verify_admin_password("correctpw", hash_path) is True


def test_verify_wrong_password(hash_path: Path) -> None:
    set_admin_password("correctpw", hash_path)
    assert verify_admin_password("wrongpw1", hash_path) is False


def test_verify_missing_file_returns_false(hash_path: Path) -> None:
    assert verify_admin_password("anything", hash_path) is False


def test_too_short_password_rejected(hash_path: Path) -> None:
    with pytest.raises(AuthError):
        set_admin_password("a" * (MIN_PASSWORD_LEN - 1), hash_path)


def test_exactly_min_length_accepted(hash_path: Path) -> None:
    pw = "a" * MIN_PASSWORD_LEN
    set_admin_password(pw, hash_path)
    assert verify_admin_password(pw, hash_path) is True


def test_overwriting_password(hash_path: Path) -> None:
    set_admin_password("firstpw1", hash_path)
    set_admin_password("secondpw", hash_path)
    assert verify_admin_password("secondpw", hash_path) is True
    assert verify_admin_password("firstpw1", hash_path) is False


def test_corrupted_hash_returns_false(hash_path: Path) -> None:
    hash_path.write_text("not-a-real-argon2-hash")
    if os.name == "posix":
        hash_path.chmod(0o600)
    assert verify_admin_password("anything", hash_path) is False


def test_empty_hash_file_returns_false(hash_path: Path) -> None:
    hash_path.write_text("")
    if os.name == "posix":
        hash_path.chmod(0o600)
    assert verify_admin_password("anything", hash_path) is False
    assert is_admin_password_set(hash_path) is False


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only permission check")
def test_refuses_world_readable_hash(hash_path: Path) -> None:
    set_admin_password("secret12", hash_path)
    hash_path.chmod(0o644)
    with pytest.raises(AuthError, match="insecure"):
        verify_admin_password("secret12", hash_path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only permission check")
def test_set_writes_0600(hash_path: Path) -> None:
    set_admin_password("secret12", hash_path)
    mode = hash_path.stat().st_mode & 0o777
    assert mode == 0o600
