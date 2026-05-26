#!/usr/bin/env python3
"""USB Defense — first-run setup ceremony.

Run as root after install. Idempotent only with --reset: it refuses to
overwrite an existing admin password by default, so accidentally running
this twice cannot lock the operator out of their own machine.

What it does, in order:
  1. Prompt for an admin password (twice, hidden input).
  2. Generate the master HMAC key for whitelist signing.
  3. Initialize an empty signed whitelist if none exists.
  4. Generate a one-time paper recovery code and DISPLAY it.

The recovery code is shown EXACTLY ONCE — write it down on paper and
keep it somewhere safe. After a single use it is invalidated and you
must run `setup.py --regenerate-recovery` to create a new one.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
# Allow running directly from the repo source tree without installation:
# add ../ to sys.path so `import usbguard_defense` resolves.
sys.path.insert(0, str(HERE.parent))


from usbguard_defense.auth import (  # noqa: E402
    MIN_PASSWORD_LEN,
    is_admin_password_set,
    set_admin_password,
)
from usbguard_defense.config import (  # noqa: E402
    ADMIN_HASH_PATH,
    MASTER_KEY_PATH,
    RECOVERY_SEED_HASH_PATH,
    WHITELIST_PATH,
    WHITELIST_SIG_PATH,
)
from usbguard_defense.integrity import ensure_master_key, sign  # noqa: E402
from usbguard_defense.recovery import generate_new, is_set as recovery_is_set  # noqa: E402


def _die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _require_root() -> None:
    if os.geteuid() != 0:
        _die("must run as root (try: sudo python3 scripts/setup.py)")


def _prompt_password() -> str:
    while True:
        pw = getpass.getpass("New admin password: ")
        if len(pw) < MIN_PASSWORD_LEN:
            print(f"  Password must be at least {MIN_PASSWORD_LEN} characters.")
            continue
        confirm = getpass.getpass("Confirm admin password: ")
        if pw != confirm:
            print("  Passwords do not match. Try again.")
            continue
        return pw


def _init_signed_whitelist(master_key: bytes) -> None:
    if WHITELIST_PATH.exists() and WHITELIST_SIG_PATH.exists():
        return  # already initialized — leave existing devices alone
    WHITELIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"version": 1, "devices": []}, indent=2).encode("utf-8")
    tmp = WHITELIST_PATH.with_suffix(".json.tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, WHITELIST_PATH)
    os.chmod(WHITELIST_PATH, 0o600)
    sig = sign(payload, master_key)
    tmp_sig = WHITELIST_SIG_PATH.with_suffix(".sig.tmp")
    tmp_sig.write_text(sig)
    os.replace(tmp_sig, WHITELIST_SIG_PATH)
    os.chmod(WHITELIST_SIG_PATH, 0o600)


def _display_recovery_code(code: str) -> None:
    bar = "=" * 60
    print()
    print(bar)
    print("PAPER RECOVERY CODE — WRITE THIS DOWN NOW".center(60))
    print(bar)
    print()
    print(f"        {code}")
    print()
    print("This code is shown ONLY ONCE.")
    print("If you lose every unlock-key USB AND forget your admin")
    print("password, this 16-character code will let you clear a")
    print("lockdown one time. After a single use it is destroyed")
    print("and you must run:")
    print()
    print("    sudo python3 scripts/setup.py --regenerate-recovery")
    print()
    print("to create a new one.")
    print(bar)
    print()
    input("Press Enter once you have written the code down... ")


def cmd_setup(args: argparse.Namespace) -> int:
    _require_root()

    existing_secrets = (
        is_admin_password_set()
        or MASTER_KEY_PATH.exists()
        or recovery_is_set()
    )
    if existing_secrets and not args.reset:
        _die(
            "USB Defense is already set up. Refusing to overwrite.\n"
            "  - To change ONLY the recovery code: --regenerate-recovery\n"
            "  - To wipe and start over (loses all secrets): --reset"
        )

    if args.reset:
        for p in (ADMIN_HASH_PATH, MASTER_KEY_PATH, RECOVERY_SEED_HASH_PATH):
            try: p.unlink()
            except FileNotFoundError: pass
        # Whitelist itself we leave alone — the operator's enrolled USBs
        # survive a reset of the secrets. The sig will be regenerated below.
        try: WHITELIST_SIG_PATH.unlink()
        except FileNotFoundError: pass

    print("Setting up USB Defense...")
    print()
    print("Step 1/4: Admin password")
    pw = _prompt_password()
    set_admin_password(pw)
    print("  Admin password set.")
    print()

    print("Step 2/4: Master integrity key")
    key = ensure_master_key()
    print(f"  Master key stored at {MASTER_KEY_PATH}")
    print()

    print("Step 3/4: Signed whitelist")
    _init_signed_whitelist(key)
    print(f"  Whitelist initialised at {WHITELIST_PATH}")
    print(f"  Signature at {WHITELIST_SIG_PATH}")
    print()

    print("Step 4/4: Paper recovery code")
    code = generate_new()
    _display_recovery_code(code)

    print("Setup complete. Start the daemon with:")
    print("    sudo systemctl enable --now usb-defense")
    return 0


def cmd_regenerate_recovery(_args: argparse.Namespace) -> int:
    _require_root()
    if not is_admin_password_set():
        _die("admin password not set — run full setup first")
    code = generate_new()
    _display_recovery_code(code)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe existing admin password, master key, and recovery code "
             "and re-run setup from scratch. Whitelist entries are preserved.",
    )
    parser.add_argument(
        "--regenerate-recovery",
        action="store_true",
        help="Only generate and display a new paper recovery code. Leaves "
             "admin password and whitelist untouched.",
    )
    args = parser.parse_args(argv)

    if args.regenerate_recovery:
        return cmd_regenerate_recovery(args)
    return cmd_setup(args)


if __name__ == "__main__":
    sys.exit(main())
