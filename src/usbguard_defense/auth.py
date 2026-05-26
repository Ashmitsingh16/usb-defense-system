"""Admin password storage and verification (argon2id).

Phase 1 of v0.2 hardening. Replaces the v0.1 placeholder where any local
process holding the IPC token environment variable could call `force_unlock`.

Threat model recap:
- The hash file lives at /etc/usb-defense/admin.hash, 0600 root:root.
- A non-root local user cannot read it, so offline cracking requires
  already-elevated privileges.
- A rogue root user CAN read the hash. argon2id makes offline brute force
  expensive; that is the best we can do on a single airgapped machine.
- Verification refuses to run if the file is group- or world-readable —
  fails closed so a misconfigured install doesn't silently weaken auth.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .config import ADMIN_HASH_PATH


MIN_PASSWORD_LEN = 8


_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=2,
)


class AuthError(Exception):
    """Raised for misconfiguration or policy violations (not for wrong passwords)."""


def set_admin_password(password: str, path: Path = ADMIN_HASH_PATH) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise AuthError(
            f"password must be at least {MIN_PASSWORD_LEN} characters"
        )
    encoded = _HASHER.hash(password)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(encoded)
    os.replace(tmp, path)
    _restrict_perms(path)


def verify_admin_password(password: str, path: Path = ADMIN_HASH_PATH) -> bool:
    if not path.exists():
        return False
    if _perms_too_loose(path):
        raise AuthError(
            f"{path} permissions are insecure — refusing to verify "
            "(file must be 0600 root:root)"
        )
    try:
        stored = path.read_text().strip()
    except OSError:
        return False
    if not stored:
        return False
    try:
        _HASHER.verify(stored, password)
        return True
    except VerifyMismatchError:
        return False
    except InvalidHashError:
        return False


def is_admin_password_set(path: Path = ADMIN_HASH_PATH) -> bool:
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError:
        return False


def _restrict_perms(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except (OSError, NotImplementedError):
        pass


def _perms_too_loose(path: Path) -> bool:
    if os.name != "posix":
        return False
    try:
        mode = path.stat().st_mode
    except OSError:
        return True
    return bool(mode & (stat.S_IRWXG | stat.S_IRWXO))
