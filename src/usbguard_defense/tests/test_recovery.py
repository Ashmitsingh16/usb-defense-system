"""Tests for the paper recovery code module. Cross-platform."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from usbguard_defense.recovery import (
    CODE_CHARS,
    CROCKFORD,
    GROUP,
    RecoveryError,
    _normalize,
    generate_new,
    is_set,
    verify_and_consume,
)


@pytest.fixture
def seed_path(tmp_path: Path) -> Path:
    return tmp_path / "recovery_seed.hash"


def test_generate_returns_grouped_format(seed_path: Path) -> None:
    code = generate_new(seed_path)
    parts = code.split("-")
    assert len(parts) == CODE_CHARS // GROUP
    for part in parts:
        assert len(part) == GROUP


def test_generate_uses_only_crockford_chars(seed_path: Path) -> None:
    code = generate_new(seed_path)
    body = code.replace("-", "")
    assert len(body) == CODE_CHARS
    assert all(ch in CROCKFORD for ch in body)


def test_is_set_after_generate(seed_path: Path) -> None:
    assert is_set(seed_path) is False
    generate_new(seed_path)
    assert is_set(seed_path) is True


def test_verify_correct_code(seed_path: Path) -> None:
    code = generate_new(seed_path)
    assert verify_and_consume(code, seed_path) is True


def test_verify_consumes_on_success(seed_path: Path) -> None:
    code = generate_new(seed_path)
    assert verify_and_consume(code, seed_path) is True
    assert is_set(seed_path) is False
    assert verify_and_consume(code, seed_path) is False


def test_verify_wrong_code_does_not_consume(seed_path: Path) -> None:
    generate_new(seed_path)
    assert verify_and_consume("0000-0000-0000-0000", seed_path) is False
    assert is_set(seed_path) is True


def test_verify_missing_file(seed_path: Path) -> None:
    assert verify_and_consume("0000-0000-0000-0000", seed_path) is False


def test_verify_accepts_lowercase_input(seed_path: Path) -> None:
    code = generate_new(seed_path)
    assert verify_and_consume(code.lower(), seed_path) is True


def test_verify_accepts_input_without_hyphens(seed_path: Path) -> None:
    code = generate_new(seed_path)
    body = code.replace("-", "")
    assert verify_and_consume(body, seed_path) is True


def test_verify_accepts_input_with_extra_spaces(seed_path: Path) -> None:
    code = generate_new(seed_path)
    spaced = " " + code.replace("-", "  ") + "\n"
    assert verify_and_consume(spaced, seed_path) is True


def test_normalize_handles_crockford_ambiguity() -> None:
    assert _normalize("oi-ll-uu") == "01" + "11" + "VV"


def test_corrupted_hash_returns_false(seed_path: Path) -> None:
    seed_path.write_text("not-an-argon2-hash")
    if os.name == "posix":
        seed_path.chmod(0o600)
    assert verify_and_consume("ABCD-EFGH-1234-5678", seed_path) is False


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only permission check")
def test_refuses_world_readable_seed(seed_path: Path) -> None:
    code = generate_new(seed_path)
    seed_path.chmod(0o644)
    with pytest.raises(RecoveryError, match="insecure"):
        verify_and_consume(code, seed_path)
