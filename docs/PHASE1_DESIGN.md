# Phase 1 Design — USB Defense v0.2 (Pilot-Ready Hardening)

**Status:** Design — to be reviewed by project guide / senior before code lands
**Author:** Ratnesh Sharma
**Date:** 2026-05-26
**Target tag:** `v0.2.0`

---

## 1. Goal

Take the current academic prototype (`v0.1.4`) and close the security gaps that
prevent it from being deployed for a **small pilot at a defense contractor
workstation**. After Phase 1, the system should be:

- **Tamper-evident** at the file level (HMAC-signed whitelist).
- **Auth-gated** for every sensitive operation (admin password before
  whitelist edits, before lockdown override).
- **Recovery-safe** (paper code + recovery password if all unlock USBs are
  lost).
- **Bypass-resistant** at the user level (TTY VT-switch blocked during
  lockdown, daemon hardened).

Phase 1 is **single-machine, fully airgapped**. No network code is added; the
existing code is reviewed to ensure nothing reaches out to the network.

## 2. Threat model — updated

| Attacker | In scope | Mitigation |
|---|---|---|
| Opportunistic outsider with physical access | **YES — primary** | USBGuard kernel block + lockdown overlay + alarm |
| BadUSB / virus pen drive | **YES — primary** | VID:PID:Serial check, HID-class flagging, append-only event log |
| Curious office user trying to whitelist their own USB | **YES — new in v0.2** | Admin password gate on UI; signed whitelist file |
| Rogue admin with root | **DETECT-ONLY** | HMAC-signed whitelist makes silent edit impossible; tamper is logged. Full prevention needs off-machine audit shipping → out of Phase 1 scope (airgapped). |
| Network attacker | **OUT** | Workstation is airgapped. No network code in repo. |
| Firmware-level USB attack (sub-USB layer) | **OUT** | Mentioned in REPORT §7.2 as accepted limitation. |
| Hardware keylogger / supply-chain compromise | **OUT** | REPORT §7.2 — accepted. |

## 3. Authentication model

One password + one paper code (kept deliberately small — student project,
no paid hardware, no budget for fancy ceremonies):

| Secret | Power | Stored as |
|---|---|---|
| **Admin password** | Edit whitelist, change settings, unlock lockdown | argon2id hash at `/etc/usb-defense/admin.hash` |
| **Paper recovery code** | Unlock lockdown ONLY, one-time use, regenerates after use. The "you lost all your unlock USBs AND forgot the password" escape hatch. | argon2id hash at `/etc/usb-defense/recovery_seed.hash` |

Both are set at install-time via a setup wizard. The wizard refuses to
overwrite existing hashes without a `--reset` flag (which itself requires
confirmation).

### Why argon2id?
- Memory-hard, side-channel resistant.
- Defense-of-record standard (recommended by OWASP, NIST SP 800-63B Appendix B).
- `argon2-cffi` has Windows + Linux wheels so unit tests run cross-platform.

### Why HMAC, not GPG, for whitelist signing?
- GPG needs a key-management ceremony (offline air-gapped key, etc.) that's
  out of scope for a single-machine pilot.
- HMAC-SHA256 with a key **derived from the admin password via PBKDF2** is
  enough to make "edit JSON by hand" attacks detectable. The key is never
  stored on disk — it is re-derived in-memory from the admin password each
  time the daemon needs to verify, so a snapshot of the disk does not reveal
  it.
- Upgrade path to GPG is documented in Phase 4 backlog.

## 4. Lockdown unlock paths

After Phase 1, lockdown can be cleared by **any of**:

1. **Authorized unlock-key USB** (existing, unchanged) — plug in a USB whose
   whitelist entry has `can_unlock: true`.
2. **Admin password** (new) — button on lockdown overlay → password dialog.
3. **Paper recovery code** (new) — button on lockdown overlay → 12-word
   input. After successful verify, the code is invalidated and the admin
   is told to generate a new one. (Safety net for "lost all USBs AND
   forgot the password".)

## 5. File layout (Phase 1)

```
/etc/usb-defense/
  config.yaml             unchanged
  whitelist.json          unchanged shape
  whitelist.sig           NEW — HMAC-SHA256 over whitelist.json, hex
  admin.hash              NEW — argon2id
  recovery_seed.hash      NEW — argon2id, plus a "consumed" marker file
```

All files: `0600 root:root`. Daemon refuses to start if perms are weaker.

## 6. New modules (src/usbguard_defense/)

| File | Responsibility |
|---|---|
| `auth.py` | argon2id hash/verify for the admin password |
| `integrity.py` | HMAC sign/verify of whitelist.json |
| `recovery.py` | 12-word seed generate/verify/consume |
| `scripts/setup.py` | First-run interactive ceremony (called by install.sh) |
| `tests/test_auth.py` | unit tests, cross-platform |
| `tests/test_integrity.py` | unit tests, cross-platform |
| `tests/test_recovery.py` | unit tests, cross-platform |

Existing files touched:

| File | Change |
|---|---|
| `whitelist.py` | `_load` verifies HMAC; `save` rewrites HMAC; both take an `auth_key` parameter |
| `daemon.py` | New IPC commands: `verify_password`, `add_whitelist_entry`, `remove_whitelist_entry`, `unlock_with_password`, `unlock_with_seed`. `force_unlock` removed (legacy env-var auth replaced by real password verify). Daemon ships sd_notify pings for watchdog. |
| `ipc.py` | Socket mode tightened from `0666` → `0660` with a new `usbdefense` group |
| `ui/whitelist_mgr.py` | Add/Remove prompts for admin password via `QInputDialog`, sends new IPC command |
| `ui/lockdown.py` | Two new buttons: "Unlock with password" and "Unlock with recovery code" (paper code) |
| `systemd/usb-defense.service` | Hardening directives + `Restart=always` + `WatchdogSec=30` |
| `scripts/install.sh` | Installs `python3-argon2-cffi` (or via pip), invokes setup wizard at end |
| `pyproject.toml` / `requirements.txt` | Adds `argon2-cffi>=23.1.0` |
| `config.py` | New path constants for the three hash files |

## 6.1 Event-log schema (v0.2.0 catalog)

The append-only event log at `/var/log/usb-defense/events.log` carries
one JSON object per line. The `type` field selects the schema. New
types in v0.2.0 are marked **NEW**. This catalog is what an incident
responder reads when investigating a forensic case.

| `type` | Triggered when | Fields beyond `ts` + `type` |
|---|---|---|
| `AUTHORIZED` | Whitelisted USB plugged in | full device dict + `label` |
| `UNAUTHORIZED` | Unknown USB plugged in | full device dict |
| `REMOVE` | Any USB removed | full device dict |
| `WHITELIST_TAMPER` **NEW** | Daemon load detected sig mismatch | `detected_at` (`startup` / `runtime`) |
| `WHITELIST_ADD` **NEW** | Whitelist gained an entry via IPC | `entry_id`, `label` |
| `WHITELIST_REMOVE` **NEW** | Whitelist entry removed via IPC | `entry_id` |
| `AUTH_FAILURE` **NEW** | Wrong admin password supplied on a write | `op` (e.g. `add_whitelist_entry`) |
| `UNLOCK_SUCCESS` **NEW** | Lockdown cleared via password or paper code | `method` (`password` / `paper_code`) |
| `UNLOCK_AUTH_FAILURE` **NEW** | Wrong password or code on an unlock attempt | `method` |
| `SIMULATOR_BLOCKED` **NEW** | `simulate_event` IPC arrived while `simulator_enabled=false` | `reason` |

A burst of `AUTH_FAILURE` followed by `WHITELIST_ADD` is the canonical
"someone is trying to guess the admin password" signature.

A `WHITELIST_TAMPER` with `detected_at: startup` after an admin
maintenance window indicates either an attempted attack or a botched
backup-restore of `whitelist.json` without its `.sig` sidecar.

## 7. Test plan

**Unit (Windows-runnable):**
- `test_auth.py`: set → verify (good + bad), is_set, refuse weak hash params, refuse passwords < 8 chars.
- `test_integrity.py`: round-trip, missing sig rejected, mutated payload rejected, wrong key rejected.
- `test_recovery.py`: generate produces 12 words from the official list, verify+consume is one-shot, double-consume rejected.

**Integration (Rocky VM):**
- Fresh `install.sh` → setup wizard → all three hashes present, 0600 root:root.
- Plug unauthorized USB → lockdown.
- Unlock with admin password → cleared.
- Plug unauthorized again → lockdown.
- Unlock with paper code → cleared, admin told to write down a new one.
- Plug unauthorized again → lockdown.
- Unlock with `can_unlock=true` USB → cleared.
- Tamper test: `sudo nano /etc/usb-defense/whitelist.json` adds a fake entry,
  `sudo systemctl restart usb-defense` → daemon logs `WHITELIST_TAMPER` and
  refuses to load whitelist (fails closed: every USB triggers lockdown).
- TTY test: trigger lockdown, try `Ctrl+Alt+F3` → no login prompt.

## 8. Out of Phase 1 scope (parked for later)

- Central whitelist sync (Phase 4)
- Remote audit log shipping to SIEM (Phase 4 — needs network)
- YubiKey hardware token support (Phase 3)
- GPG-signed whitelist with offline admin key (Phase 3)
- RPM packaging + signed repo (Phase 2)
- Two-person rule for whitelist changes (Phase 5)

## 9. Compliance note (informational only — no spend required)

The phrase "defense-grade" is a **design aspiration**, not a certification.
For an academic pilot, no audit is required. Before any commercial sale or
real defense-contractor rollout, three things you should *know about* exist
(but don't have to do now, and no money needs to leave your pocket for
Phase 1):

- **CERT-In empanelled audit** — third-party security review. Cost to the
  buyer, not to you. Required for some Indian-government procurement.
- **IT Act 2000 §43A** — applies if the workstation stores personal data.
- **Common Criteria / EAL** — needed only if MoD procurement explicitly
  requires it. Most contractor deployments don't.

Mentioned here so future-you (or your senior) knows the path exists. Not
a Phase 1 task and zero spend.

## 10. Acceptance criteria for Phase 1

- All 8 items in `TaskList` completed.
- All unit tests pass (existing 44 + new ~15 = ~59 passing).
- Manual integration test on Rocky VM passes every step in §7.
- `CHANGELOG.md` has a `v0.2.0` entry.
- `REPORT.md` §7.2 updated: items 1, 2 (admin password), 3 (TTY), 4
  (HMAC tamper) move from "future work" to "implemented".
- Tag `v0.2.0` cut.

---

**Sign-off (pending review):**

- [ ] Project guide
- [ ] Senior
- [ ] Self — Ratnesh
