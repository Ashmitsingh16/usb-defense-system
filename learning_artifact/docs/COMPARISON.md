# netwatch vs Ashmit's USB-Defense System

Engineering contrast prepared 2026-05-21. Reference: Ashmit's
`CRITICAL_REVIEW.md` (2,495 LOC, v0.1.4, Rocky Linux 9, Qt-based).
Different threat model — USB vs LAN — but the engineering questions
("how do you authenticate the operator?", "how do you survive a hostile
local user?") generalize. We answer them.

## Size

| Metric | Ashmit | netwatch | Delta |
|---|---|---|---|
| LOC (source) | 2,495 | ~890 (incl. tests, TUI) | -64% |
| LOC (production code only) | ~1,800 | ~580 | -68% |
| Source modules | 11 | 11 | flat |
| Test files | 4 (no `test_daemon`) | 8 (incl. daemon) | +4 |
| Daemon test coverage | 0% | 74% | +74 pp |

Note: the Ashmit project's UI is a Qt dialog. We pay a few hundred lines
in `tui.py` for a richer terminal UI — and still come out a third of the
size.

## Attack-surface contrast

Both projects watch for an unauthorised endpoint and lock the operator
out. The exploit-significant differences:

### 1. Unlock-token storage

| | Ashmit | netwatch |
|---|---|---|
| Form | Plaintext env var (`USB_DEFENSE_ADMIN_TOKEN`) | bcrypt hash (cost 12) on disk |
| Path | `/proc/<pid>/environ` (world-readable) | `/etc/netwatch/auth.json` (mode 0640, root:netwatch) |
| Extraction by local user | Trivial (`cat /proc/$(pgrep ...)/environ`) | Requires offline bcrypt brute |
| Verification | String equality | `bcrypt.checkpw` (constant-time) |

### 2. IPC

Ashmit ships a 0666 (world-writable) Unix-domain socket and ANY local
user can `force_unlock`. `netwatch` does not expose an IPC socket at all
in v0.1.0 — the TUI lives in the same process as the daemon. When IPC
arrives in a future release, it will be 0660 + group-owned. Smaller
attack surface today; intentional defer.

### 3. Privilege model

| | Ashmit | netwatch |
|---|---|---|
| User | root | dedicated `netwatch` system user |
| Capabilities | full root | `CAP_NET_RAW` + `CAP_NET_ADMIN` only |
| Filesystem | full RW | `ProtectSystem=strict` + 3 explicit RW paths |
| Syscalls | unrestricted | `SystemCallFilter=@system-service` minus 5 categories |
| `NoNewPrivileges` | not set | `true` |
| `MemoryDenyWriteExecute` | not set | `true` |

A pyudev / PyYAML interpreter bug in Ashmit's daemon = full root. In
`netwatch` the same class of bug grants only the ability to send raw
packets and admin nftables.

### 4. Rate-limiting

Ashmit: none. Plug/unplug → relock → alarm replay → operator
desensitisation, and on log rotation absence, eventual disk-exhaustion.
`netwatch`: 5-second debounce per MAC + `_trigger_response` is a no-op
while already locked. Plus log rotation (10 MB × 5 = 50 MB cap).

## Per-flaw walkthrough

The 10 flaws from `CRITICAL_REVIEW.md`, mapped to netwatch's behaviour:

| # | Ashmit Severity | Flaw | netwatch's Answer |
|---|---|---|---|
| 1 | **CRITICAL** | Plaintext admin env var | `auth.py` — bcrypt hash; never read into env; constant-time verify; tested. |
| 2 | **CRITICAL** | World-readable IPC | No IPC socket in v0.1.0. Future socket is documented as 0660 + group-owned. |
| 3 | **HIGH** | Blind trust of USB serial | Different threat model (LAN MAC). MAC spoofing IS feasible, and we say so explicitly in README "Out of scope: layer-2 MAC hijacks." Honesty > false security. |
| 4 | **HIGH** | No alert rate-limiting | `Daemon.ALERT_DEBOUNCE_SECONDS = 5.0`; `_recent_alerts` deque; `_trigger_response` short-circuits while locked. Tested in `test_duplicate_alerts_debounced`. |
| 5 | **MEDIUM** | Daemon runs as root | Dedicated `netwatch` system user; ambient `CAP_NET_RAW` + `CAP_NET_ADMIN` only; `NoNewPrivileges=true`; full `ProtectSystem` + syscall filter. |
| 6 | **MEDIUM** | Wayland visual-only lockdown | We don't draw an X/Wayland overlay at all. The "lock" is a network-level freeze + a TUI-level unlock gate. No display server in the threat path. |
| 7 | **MEDIUM** | No log rotation | `RotatingFileHandler(maxBytes=10MB, backupCount=5)`. Configurable. Adversary cannot exhaust disk via alert spam. |
| 8 | LOW | `remove()` returns silently | Both `Daemon.remove_whitelist` and `cli.whitelist remove` return + surface a non-zero exit code with a stderr message when the MAC isn't present. Tested. |
| 9 | LOW | Untyped YAML loader | All config goes through pydantic v2 `Config.model_validate`. Invalid types raise at load. Tested with `test_load_rejects_non_mapping` + `test_negative_interval_rejected`. |
| 10 | LOW | No daemon tests | `tests/test_daemon.py` exercises: alert, lock, debounce, unlock-good, unlock-bad, lockout, force-freeze, whitelist, rebuild, run+stop, malformed-MAC, double-lock no-op. Twelve tests on the daemon alone. |

## What we don't claim

- We don't claim parity with a commercial NIDS (Suricata, Zeek). Those
  are deep packet inspectors. `netwatch` is a tripwire.
- We don't pretend the bcrypt file at 0640 survives a local-root
  attacker. It doesn't — once an attacker is root, they own the daemon.
  We say so in the README. Ashmit's claim that USBGuard-blocked devices
  are "blocked at the kernel level" is similarly only true relative to
  non-root users.
- We don't pretend our scapy sensors run on Windows. They don't. The
  test suite runs on Windows because every sensor is dependency-injected
  with a fake reader / scanner.

## Where Ashmit's project is solid

Worth saying out loud: the architecture document for the USB-defense
project is clearer than most production code we've seen. The OO layout
(monitor / whitelist / ipc / event_log) is good. The persistent
lockdown-flag idea is good. The journald-plus-file logging is good. We
kept the same shape and fixed the broken bits.

---

*— Jarvis, 2026-05-21*
