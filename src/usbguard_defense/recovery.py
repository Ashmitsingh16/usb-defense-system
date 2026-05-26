"""Paper recovery code: 16-char Crockford Base32, displayed once at setup.

This is the "I lost every unlock-key USB AND forgot the admin password" escape
hatch. The plaintext code is shown to the admin exactly once during setup;
they write it on paper and lock it away. After a single successful use it is
invalidated and the admin is told to generate a new one.

Format: XXXX-XXXX-XXXX-XXXX (16 Crockford-Base32 chars + 3 hyphens).
- Crockford Base32 omits I, L, O, U to avoid handwritten-paper transcription
  errors. The normalizer also accepts the lowercased and ambiguous forms a
  human might type back (O→0, I/L→1, U→V) so a slightly miscopied code
  still works.
- 16 chars × 5 bits = 80 bits of entropy. argon2id at rest makes offline
  brute force infeasible on consumer hardware.
- One-time use: after verify_and_consume() the hash file is deleted so the
  same paper code can't be used twice.
"""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .config import RECOVERY_SEED_HASH_PATH


CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_CHARS = 16
GROUP = 4


_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=2,
)


class RecoveryError(Exception):
    """Raised on misconfiguration or insecure file permissions."""


def generate_new(path: Path = RECOVERY_SEED_HASH_PATH) -> str:
    """Generate a fresh recovery code, hash it to disk, return the plaintext.

    The plaintext is returned so the caller can DISPLAY IT ONCE. It is not
    stored anywhere else.
    """
    raw = "".join(secrets.choice(CROCKFORD) for _ in range(CODE_CHARS))
    display = "-".join(raw[i:i + GROUP] for i in range(0, CODE_CHARS, GROUP))
    encoded = _HASHER.hash(_normalize(display))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(encoded)
    os.replace(tmp, path)
    _restrict_perms(path)
    return display


def is_set(path: Path = RECOVERY_SEED_HASH_PATH) -> bool:
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError:
        return False


def verify_and_consume(code: str, path: Path = RECOVERY_SEED_HASH_PATH) -> bool:
    """Verify the code. On success, DELETE the hash file (one-time use)."""
    if not path.exists():
        return False
    if _perms_too_loose(path):
        raise RecoveryError(
            f"{path} permissions are insecure — must be 0600 root:root"
        )
    try:
        stored = path.read_text().strip()
    except OSError:
        return False
    if not stored:
        return False
    try:
        _HASHER.verify(stored, _normalize(code))
    except (VerifyMismatchError, InvalidHashError):
        return False
    # Consume — delete the hash file so the same paper code can't be re-used.
    try:
        path.unlink()
    except OSError:
        pass
    return True


def _normalize(code: str) -> str:
    """Strip whitespace and hyphens, uppercase, fix Crockford ambiguity."""
    s = "".join(ch for ch in code if not ch.isspace() and ch != "-")
    s = s.upper()
    s = s.replace("O", "0").replace("I", "1").replace("L", "1").replace("U", "V")
    return s


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
