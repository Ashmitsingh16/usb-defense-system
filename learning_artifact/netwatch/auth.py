"""bcrypt-based unlock authentication.

Ashmit's #1 critical flaw was a plaintext env-var unlock token. We do the
opposite: the password is bcrypt-hashed at install time, stored mode-0600,
and verified in constant time. No plaintext lives anywhere on disk, in
process memory longer than necessary, or in env vars.
"""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

import bcrypt


@dataclass(frozen=True)
class AuthRecord:
    hash: str   # bcrypt hash string (already includes salt + cost)
    created: str  # ISO timestamp

    def to_json(self) -> str:
        return json.dumps({"hash": self.hash, "created": self.created}, indent=2)

    @classmethod
    def from_json(cls, blob: str) -> "AuthRecord":
        data = json.loads(blob)
        if not isinstance(data, dict) or "hash" not in data:
            raise ValueError("auth record corrupt: missing 'hash'")
        return cls(hash=str(data["hash"]), created=str(data.get("created", "")))


def hash_password(password: str, *, cost: int = 12) -> str:
    """Return a bcrypt hash for `password`. Cost 12 ~ 250 ms on modern CPUs."""
    if not password:
        raise ValueError("password must not be empty")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(cost)).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time bcrypt verification. Never raises on bad hash — returns False."""
    if not password or not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def write_auth(path: Path, password: str) -> AuthRecord:
    """Atomically write a new auth record at `path` with mode 0600."""
    from datetime import datetime, timezone

    record = AuthRecord(
        hash=hash_password(password),
        created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{secrets.token_hex(4)}")
    tmp.write_text(record.to_json(), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except (OSError, NotImplementedError):
        # Windows: chmod is best-effort. The systemd unit handles real perms on Linux.
        pass
    os.replace(tmp, path)
    return record


def read_auth(path: Path) -> AuthRecord:
    if not path.exists():
        raise FileNotFoundError(f"auth record not found at {path}; run `netwatch setpassword`")
    return AuthRecord.from_json(path.read_text(encoding="utf-8"))


def verify_at(path: Path, password: str) -> bool:
    """Load record at `path` and verify `password`. Returns False on any failure."""
    try:
        rec = read_auth(path)
    except (FileNotFoundError, ValueError):
        return False
    return verify_password(password, rec.hash)
