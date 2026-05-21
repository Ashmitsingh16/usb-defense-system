from __future__ import annotations

from pathlib import Path

import pytest

from netwatch import auth


def test_hash_and_verify_roundtrip() -> None:
    h = auth.hash_password("hunter2", cost=4)
    assert auth.verify_password("hunter2", h)
    assert not auth.verify_password("wrong", h)


def test_empty_password_rejected() -> None:
    with pytest.raises(ValueError):
        auth.hash_password("")
    assert not auth.verify_password("", "anything")
    assert not auth.verify_password("x", "")


def test_bad_hash_returns_false() -> None:
    assert not auth.verify_password("x", "not-a-real-hash")


def test_write_and_read(tmp_path: Path) -> None:
    p = tmp_path / "auth.json"
    rec = auth.write_auth(p, "s3cret")
    assert p.exists()
    loaded = auth.read_auth(p)
    assert loaded.hash == rec.hash
    assert auth.verify_at(p, "s3cret")
    assert not auth.verify_at(p, "nope")


def test_verify_at_missing_file(tmp_path: Path) -> None:
    assert not auth.verify_at(tmp_path / "missing.json", "x")


def test_read_auth_corrupt(tmp_path: Path) -> None:
    p = tmp_path / "auth.json"
    p.write_text("{}")
    with pytest.raises(ValueError):
        auth.read_auth(p)
    assert not auth.verify_at(p, "x")


def test_write_overwrites_atomically(tmp_path: Path) -> None:
    p = tmp_path / "auth.json"
    auth.write_auth(p, "one")
    auth.write_auth(p, "two")
    assert auth.verify_at(p, "two")
    assert not auth.verify_at(p, "one")
