# Security Policy

## Threat model (current as of v0.2.0)

| Attacker | Status |
|---|---|
| Opportunistic outsider with physical access | **Defended** — USBGuard kernel block + full-screen lockdown + alarm |
| BadUSB / virus pen drive | **Defended** — VID:PID:Serial whitelist, HID-class flagging, append-only event log |
| Curious office user trying to whitelist their own USB | **Defended** — admin password (argon2id) required for all UI writes |
| Operator escaping lockdown via `Ctrl+Alt+F<N>` to a TTY | **Partially mitigated (TTY-1, known limitation)** — X11 `DontVTSwitch` + runtime getty mask are deployed but `systemd-logind` dynamically respawns gettys on VT switch, bypassing both. Proper fix (`NAutoVTs=0` + restart logind) deferred to Phase 2. |
| Operator who lost every unlock-key USB AND forgot the password | **Recoverable** — one-time 16-char paper recovery code |
| Root user editing `whitelist.json` by hand | **Detected, fail-closed** — HMAC-SHA256 signature verified on every load |
| Rogue root user who also reads `master.key` and re-signs forgeries | **Detect-only on this machine** — accepted residual risk on a single airgapped box; full prevention deferred to Phase 4 (off-machine audit log shipping, requires networking). |
| Firmware-level USB attack below the protocol layer | **Out of scope** — software cannot solve this; procurement-time choice (IronKey / Apricorn) is the mitigation. |
| Network attacker | **Out of scope** — workstation is airgapped; the repository contains no network code. |
| Hardware keylogger / supply-chain compromise of the OS | **Out of scope** — not addressable from userspace. |

### Production-deployment switch

The default `/etc/usb-defense/config.yaml` ships with `simulator_enabled: true`
so the academic-project demos work out of the box. **Before deploying to a
real pilot workstation**, edit the config to `simulator_enabled: false` and
restart the daemon. The simulator IPC path is otherwise an authentication
bypass (any user in the `usbdefense` group can fake a `lockdown_clear` event
without supplying the admin password). This is documented inline in
`config.yaml` and called out in DEPLOYMENT_RUNBOOK Phase F.

Full design rationale: [`docs/PHASE1_DESIGN.md`](docs/PHASE1_DESIGN.md).
Per-bullet engineering notes: [`docs/REPORT.md`](docs/REPORT.md) §7.

## Reporting a vulnerability

This is an academic-origin project. If you find a defect that bypasses
any of the **defended** items above (the first six rows of the table):

1. **Do not** open a public GitHub issue.
2. Email the project author with:
   - Steps to reproduce.
   - The version (`git rev-parse HEAD` and the `__version__` line from
     `src/usbguard_defense/__init__.py`).
   - The Rocky / RHEL release and any deviations from the documented
     install procedure.
3. Allow up to two weeks for an initial response before public disclosure.

Defects in **out-of-scope** items are acknowledged but not patched —
they are documented as boundaries of the design.

## Forensic event-log schema

When investigating an incident on a deployed workstation, start with:

```bash
sudo cat /var/log/usb-defense/events.log | python3 -m json.tool
```

The full catalog of `type` values and the fields each carries is in
[`docs/PHASE1_DESIGN.md` §6.1](docs/PHASE1_DESIGN.md). Quick reference:

- `WHITELIST_TAMPER` — somebody hand-edited the whitelist.
- `AUTH_FAILURE`, `UNLOCK_AUTH_FAILURE` — failed admin password attempts.
- `SIMULATOR_BLOCKED` — attempted simulator misuse on a production deployment.

A burst of `AUTH_FAILURE` followed by `WHITELIST_ADD` is the signature
of an active password-guessing attack that eventually succeeded.

## Crypto choices

- **Password hashing:** argon2id (`argon2-cffi`), `t=3`, `m=64 MiB`,
  `p=2`. Hash file `/etc/usb-defense/admin.hash`, 0600 root:root.
- **Whitelist integrity:** HMAC-SHA256 with a 32-byte random key from
  `secrets.token_bytes()`. Key at `/etc/usb-defense/master.key`,
  0600 root:root, generated once at setup and never rotated unless
  `setup.py --reset` is run.
- **Paper recovery code:** 16 characters from Crockford Base32 (no
  ambiguous I/L/O/U), 80 bits of entropy, argon2id-hashed at rest,
  deleted after a single successful verify.

All three secrets verify by reading their respective files; verification
**fails closed** if the file permissions are weaker than 0600 (POSIX
hosts only — the daemon won't run on non-POSIX).

## Compliance status

The phrase "defense-grade" in the documentation describes the **design
aspiration**, not a certification. The project has NOT undergone:

- CERT-In empanelled audit.
- Common Criteria (any EAL).
- IT Act 2000 §43A formal review.

These are organisational / commercial requirements documented in
`docs/PHASE1_DESIGN.md` §9 for future commercialisation. Phase 1 is an
academic / pilot deliverable.

## Supported versions

Only the current release (v0.2.0 once tagged; the `main` branch in the
interim) receives security fixes. v0.1.x is superseded.
