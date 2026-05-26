<!--
Marp-compatible slide deck. To render:
  npm i -g @marp-team/marp-cli
  marp docs/SLIDES.md -o slides.pdf
Or open in VS Code with the Marp extension.
-->
---
marp: true
theme: gaia
class: lead
paginate: true
backgroundColor: #0d1117
color: #c9d1d9
---

<!-- _class: lead -->

# USB Defense System

### Whitelist-enforced USB guard with full-system lockdown for Rocky Linux 9

A defense-grade hardened-workstation security layer (v0.2.0)
Ratnesh Sharma — Final Year Project

---

## The problem

- USB is the **#1 physical attack vector** in classified environments
- Three headline incidents:
  - **Stuxnet** (2010) — air-gap crossed by one infected USB
  - **BadUSB** (2014) — USB firmware can pretend to be a keyboard
  - **Insider exfiltration** — most common DLP failure mode

> *Defense workstations need a layer between the USB port and the kernel.*

---

## Threat model — what we DO defend against

| Threat | Our defense |
|---|---|
| Unauthorized mass storage | Whitelist by VID:PID:Serial → kernel block |
| Walk-away attack | Full-screen lockdown + alarm + input grab |
| Lost workstation | Authorized USB key required to unlock |
| Curious user adds own USB | **argon2id admin password gate** (v0.2) |
| Root hand-edits whitelist | **HMAC-SHA256 sig, fail-closed** (v0.2) |
| Operator escapes via Ctrl+Alt+F3 | **X11 DontVTSwitch + getty mask** (v0.2) |
| Lost every unlock USB + forgot password | **Paper recovery code, one-time** (v0.2) |
| Audit / forensics | Dual log: journald + append-only flat file |
| Daemon kill | systemd notify+watchdog + on-disk lockdown flag |

---

## Threat model — what we DON'T defend against (honest)

| Threat | Why not | Mitigation |
|---|---|---|
| BadUSB firmware spoofing of authorized device | Software cannot detect spoofed firmware | Hardware-validated USBs (IronKey) |
| Offline disk attack | Out of software scope | Full-disk encryption (LUKS) |
| Rogue root user re-signing the whitelist | Single-machine airgap; needs off-machine audit | Phase 4 SIEM forwarding (requires network) |
| Hardware keylogger | Software cannot see this | Physical inspection |
| Insider with authorized USB | Out of scope | DLP, file-level audit |

**Stating these explicitly = academic rigour.**

---

## Four-layer defense in depth

```
┌─────────────────────────────────────────┐
│  PyQt5 UI       USB Defense Daemon       │  USER
│  Dashboard ◄──► pyudev monitor           │  SPACE
│  Lockdown        whitelist matcher       │
│                  lockdown coordinator    │
│                  dual logger             │
│                       │                  │
│                       ▼ subprocess       │
│                  USBGuard (CLI)          │
└─────────────────────────────────────────┘
                       │
┌─────────────────────────────────────────┐
│  USB subsystem │ udev │ authorize/block  │  KERNEL
└─────────────────────────────────────────┘
```

If any one layer fails, the others still protect.

---

## Tech stack — what & why

| Component | Tech | Why this |
|---|---|---|
| Target OS | Rocky Linux 9 | RHEL-class, sector standard |
| Kernel enforcement | USBGuard | Existing kernel daemon; we use it as the engine |
| Event monitor | pyudev | Event-driven, zero-CPU idle |
| Daemon | Python 3 | Speed of iteration; bottleneck is human reaction |
| UI | PyQt5 | Dark theme + true fullscreen modal overlay |
| Service mgmt | systemd | Hardening primitives (`ProtectSystem=strict`) |
| IPC | Unix socket + JSON lines | Local-only, no network attack surface |
| Audit | journald + `chattr +a` flat file | Tamper-resistant — even root logs the bypass |

---

## Data flow — authorized USB

1. Kernel `udev` fires `add` event
2. USBGuard sees matching allow → drivers bind → `/dev/sdb` appears
3. Our daemon sees same event via pyudev (in parallel)
4. `whitelist.match(vid, pid, serial)` → entry found
5. Log: `AUTHORIZED USB inserted: Admin Backup Drive`
6. GNOME auto-mounts at `/run/media/<user>/<label>`

✅ User uses the drive normally

---

## Data flow — unauthorized USB

1. Kernel `udev` fires `add` event
2. USBGuard default `block` → **no `/dev/sdb` appears**
3. Our daemon sees same event via pyudev
4. `whitelist.match(...)` → `None`
5. **Persistent flag** written to disk
6. IPC broadcast → UI shows full-screen red overlay
7. Alarm starts (ALSA `aplay` loop)
8. Keyboard + mouse grabbed
9. Log: `UNAUTHORIZED USB inserted ... ENTERING LOCKDOWN`

🚨 System locked until authorized unlock-key USB arrives

---

## The clever bits

1. **Asymmetric trust** — `can_unlock=true` USBs clear lockdowns; regular ones only mount
2. **Paranoid restart** — kill the daemon, systemd restarts in 5 s, re-enters lockdown from on-disk flag
3. **Dual-channel detection** — USBGuard *and* pyudev independently
4. **Tamper-resistant log** — `chattr +a` blocks even root from editing the audit trail without leaving evidence
5. **systemd sandbox** — `ProtectSystem=strict`, `NoNewPrivileges`, only 3 writable dirs

---

## File layout (deployed)

```
/usr/lib/usb-defense/      ← venv + Python source + alarm.wav
/etc/usb-defense/
    ├── config.yaml         ← settings
    └── whitelist.json      ← root-owned 0600
/var/log/usb-defense/
    └── events.log          ← chattr +a, JSON lines
/var/lib/usb-defense/
    └── lockdown.flag       ← persistent (survives reboot)
/run/usb-defense/
    ├── daemon.pid
    └── ipc.sock            ← daemon ↔ UI socket
```

---

## What's been built (v0.2.0)

- ✅ Rocky Linux 9 VM ready (VirtualBox 7.2.8, ISO downloaded)
- ✅ 22 Python files — daemon (13) + PyQt5 UI (7) + helper (2)
- ✅ Installer + setup wizard + uninstaller + hardened systemd unit
- ✅ Tamper-resistant audit log + dual journald logging
- ✅ HMAC-signed whitelist, argon2id admin password, paper recovery code
- ✅ X11 + getty TTY-escape lockdown defense
- ✅ Alarm sound generated in pure Python stdlib
- ✅ **88 unit tests, all passing** (4 POSIX-only skipped on dev host)
- ✅ 9 documentation files (architecture, runbook, demos, report, install, primer, design, acceptance, security)

---

## Live demo — five scenarios

| # | Demo | Proves |
|---|---|---|
| 1 | Authorized USB | Happy path works |
| 2 | Unauthorized USB → lockdown | Core defense fires |
| 3a | Data-USB tries to unlock — fails | Asymmetric trust |
| 3b | Key-USB unlocks | Asymmetric trust |
| 4 | `kill -9` daemon during lockdown | Paranoid restart |
| 5 | BadUSB-style HID device | Policy-level catch |

---

## Honest limitations (v0.2.0 status)

- ✅ ~~Lockdown input-grab is software-only~~ — **FIXED in v0.2.0**: X11 `DontVTSwitch` + runtime getty mask blocks `Ctrl+Alt+F<N>`.
- ✅ ~~Whitelist editable by root with no detection~~ — **FIXED in v0.2.0**: HMAC-SHA256 sig + fail-closed verify. A rogue root with key access can still re-sign — that's the only residual gap, accepted on a single airgapped box.
- ⚠️ **BadUSB firmware spoofing** of authorized fingerprint defeats us
  → roadmap: hardware-validated USBs at procurement
- ⚠️ `chattr +a` requires **ext4** — Rocky 9 default is ext4 so OK on the target
- ⚠️ Wayland sessions still silently weaken `grabKeyboard` — v0.2 sidesteps by defaulting to X11 at install

All documented in `REPORT.md` §7.2 and `PHASE1_DESIGN.md` §2.

---

## Future work (post-v0.2.0)

- **Phase 2**: RPM packaging + signed yum repo, pilot on 1–3 office workstations
- **Phase 3**: YubiKey / hardware token gating for whitelist edits, GPG-signed whitelist with offline admin key
- **Phase 4**: Off-machine audit-log shipping (requires network — deferred per airgap requirement) to close the rogue-root residual gap
- **Phase 5**: Two-person rule for whitelist changes (nuclear-launch-style controls)
- Wayland compositor-level overlay via `gtk-layer-shell` (so Wayland sessions work too)
- Cross-distro packaging (Debian/Ubuntu)

---

## Numbers to remember

| Metric | Value |
|---|---|
| Version | 0.2.0 (Phase 1 hardening) |
| Python files | 22 |
| Unit tests passing | 88 (4 POSIX-only skipped on dev host) |
| Defense layers | 6 (kernel, daemon, UI, audit, password gate, HMAC integrity) |
| Logging channels | 2 (journald + chattr+a flat file) |
| Daemon-restart latency on kill | ~1 s (`RestartSec=1`) |
| Watchdog timeout | 30 s |
| USB insert → overlay latency | ~300 ms |
| Daemon RSS idle | ~30 MB |
| Open network ports | 0 |
| Password hash | argon2id (t=3, m=64 MiB, p=2) |
| Whitelist sig | HMAC-SHA256, 32-byte key |
| Recovery code entropy | 80 bits (16 Crockford-Base32) |

---

<!-- _class: lead -->

# Thank you

Questions?

Code: `~/Desktop/USB-Defense-Project/`
Docs: `docs/{ARCHITECTURE,PHASE1_DESIGN,DEPLOYMENT_RUNBOOK,DEMO_SCENARIOS,REPORT}.md`
Security policy: `SECURITY.md`
