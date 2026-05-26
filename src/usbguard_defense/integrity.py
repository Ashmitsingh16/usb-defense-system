"""HMAC-SHA256 sign/verify for the whitelist file.

Phase 1 of v0.2 hardening. The whitelist sits at /etc/usb-defense/whitelist.json
and is paired with a sidecar /etc/usb-defense/whitelist.sig containing the hex
HMAC-SHA256. The HMAC key is a 32-byte random secret at
/etc/usb-defense/master.key, 0600 root:root, generated once at setup time.

Threat model:
- A non-root local user cannot read or write any of the three files. No
  signature forgery is possible for them.
- A root user CAN read the key and forge a signature — accepted limitation
  on a single airgapped machine. The signature still detects ACCIDENTAL
  hand-edits and "I forgot to update the sig" mistakes, which is most of
  the realistic tamper surface on a pilot workstation.
- The daemon FAILS CLOSED on any verification failure: it treats the
  whitelist as empty so every USB triggers lockdown.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import stat
from pathlib import Path

from .config import MASTER_KEY_PATH


KEY_BYTES = 32


class IntegrityError(Exception):
    """Raised when the master key is missing or has insecure permissions."""


def ensure_master_key(path: Path = MASTER_KEY_PATH) -> bytes:
    """Read the master key, generating one if missing.

    Caller must be root or the path's owner — otherwise this raises.
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".key.tmp")
        tmp.write_bytes(secrets.token_bytes(KEY_BYTES))
        os.replace(tmp, path)
        _restrict_perms(path)
    if _perms_too_loose(path):
        raise IntegrityError(
            f"{path} permissions are insecure — must be 0600 root:root"
        )
    data = path.read_bytes()
    if len(data) < 16:
        raise IntegrityError(f"{path} contains an undersized key")
    return data


def sign(data: bytes, key: bytes) -> str:
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def verify(data: bytes, key: bytes, signature: str) -> bool:
    if not signature:
        return False
    try:
        expected = sign(data, key)
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(expected, signature.strip())


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
