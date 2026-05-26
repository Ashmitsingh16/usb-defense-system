# USB Defense System

Whitelist-based USB device guard with full system lockdown for Rocky Linux 9.
Designed as a defense-grade hardened workstation security layer.

**Current version: 0.2.0 — Phase 1 security hardening (code complete, awaiting VM acceptance).**

## What it does

- Watches every USB device that gets plugged in.
- Checks against a signed whitelist of authorized devices (VID:PID:Serial).
- **Allowed devices** mount normally.
- **Unknown devices** trigger:
  - Kernel-level block (via USBGuard) — device cannot bind any drivers.
  - Full-screen system lockdown — keyboard/mouse grabbed, TTY VT-switch
    disabled, getty consoles masked.
  - Audible alarm.
  - Logged event with full device fingerprint (append-only file + journald).
- **Lockdown clears via any of:**
  - A whitelisted "unlock key" USB (`can_unlock=true`).
  - The admin password (argon2id-hashed, set during install).
  - A one-time 16-character paper recovery code (Crockford Base32,
    invalidated after a single use).

## v0.2.0 hardening at a glance

| Layer | v0.1.x | v0.2.0 |
|---|---|---|
| Kernel block | USBGuard | USBGuard |
| Whitelist integrity | none | HMAC-SHA256, fail-closed on tamper |
| Admin auth | env-var token | argon2id password + PAM-style verify |
| Recovery | none | one-time paper code, argon2id-hashed |
| TTY escape | possible via `Ctrl+Alt+F<N>` | partially mitigated; **TTY-1** known gap, see CHANGELOG |
| Daemon supervision | `Restart=always` | `Type=notify` + 30 s watchdog + kernel-protect flags |
| UI write path | direct file write (0666 socket) | daemon IPC, password-gated |

## Quick links

- [Phase 1 design (v0.2.0)](docs/PHASE1_DESIGN.md) — current threat model, scope, file layout
- [Phase 1 acceptance checklist](docs/PHASE1_ACCEPTANCE.md) — what to run on the VM before tagging v0.2.0
- [Architecture (v0.1 baseline)](docs/ARCHITECTURE.md) — system design, data flow
- [Installation](docs/INSTALLATION.md) — install commands and per-step troubleshooting
- [Deployment Runbook](docs/DEPLOYMENT_RUNBOOK.md) — click-by-click VM bringup
- [Demo Scenarios](docs/DEMO_SCENARIOS.md) — scripted demos for the viva
- [Final Report](docs/REPORT.md) — academic write-up
- [Presentation Slides](docs/SLIDES.md) — Marp-compatible deck
- [Viva Cheatsheet](docs/VIVA_CHEATSHEET.md) — printable Q&A
- [Changelog](CHANGELOG.md) — what changed in each version
- [Linux Primer](docs/LINUX_PRIMER.md) — beginner Linux reference

## Running the tests

```bash
cd src
pip install -e .[dev]   # picks up argon2-cffi + pytest
python -m pytest usbguard_defense/tests -v
# 88 tests pass (4 POSIX-only skipped on Windows hosts)
```

## Source layout

```
USB-Defense-Project/
├── src/
│   ├── usbguard_defense/         # Python package
│   │   ├── daemon.py             # main daemon + IPC command dispatch
│   │   ├── monitor.py            # pyudev USB watcher
│   │   ├── whitelist.py          # whitelist + HMAC verify
│   │   ├── usbguard_iface.py     # CLI wrapper for usbguard
│   │   ├── alarm.py              # alarm sound player
│   │   ├── ipc.py                # daemon ↔ UI socket
│   │   ├── event_log.py          # append-only flat-file log
│   │   ├── config.py             # paths + YAML config loading
│   │   ├── auth.py               # argon2id admin password (v0.2)
│   │   ├── integrity.py          # HMAC sign/verify (v0.2)
│   │   ├── recovery.py           # paper recovery code (v0.2)
│   │   ├── tty_lockdown.py       # getty mask/unmask (v0.2)
│   │   ├── tests/                # 88 unit tests
│   │   └── ui/                   # PyQt5 UI
│   │       ├── main.py
│   │       ├── dashboard.py
│   │       ├── lockdown.py       # full-screen overlay + unlock buttons
│   │       ├── whitelist_mgr.py  # password-gated add/remove
│   │       ├── event_log.py
│   │       ├── settings.py
│   │       └── styles.py
│   ├── config/                   # default config files + xorg-novtswitch.conf
│   ├── systemd/                  # hardened service unit + UI autostart
│   ├── scripts/                  # install.sh, uninstall.sh, setup.py (v0.2)
│   ├── assets/                   # alarm.wav
│   ├── pyproject.toml
│   └── requirements.txt
├── docs/
└── CHANGELOG.md
```

## Install on Rocky / RHEL 9

```bash
cd USB-Defense-Project/src
sudo ./scripts/install.sh
# At step 9/9 the installer launches an interactive setup wizard:
#   - Choose an admin password (8 chars min).
#   - Write down the paper recovery code shown ONCE in the banner.
```

## Run

```bash
sudo systemctl start usb-defense
sudo systemctl status usb-defense       # expect: active (running)
usb-defense-py -m usbguard_defense.ui.main
```

## Components

| Layer | Tech |
|---|---|
| OS | Rocky Linux 9 / RHEL 9 |
| Kernel enforcement | USBGuard |
| Daemon | Python 3 + pyudev |
| UI | PyQt5, X11 (dark theme) |
| IPC | Unix socket + line-delimited JSON, password-gated commands |
| Logging | journald + append-only flat file (`chattr +a`) |
| Service mgmt | systemd notify-type + watchdog |
| Auth | argon2id (admin password), HMAC-SHA256 (whitelist) |

## Status

- [x] Phase 1 hardening — code complete, 88 unit tests passing
- [x] Architecture, installation, deployment, report, slides, cheatsheet
- [x] v0.1.4 end-to-end demos captured on Rocky VM
- [ ] **Phase 1 acceptance on Rocky VM** — see `docs/PHASE1_ACCEPTANCE.md`
- [ ] Tag `v0.2.0` after acceptance passes
- [ ] Pilot on 1–3 office workstations

## Security disclosure

This is an academic-origin prototype. See [SECURITY.md](SECURITY.md) for
the threat model summary, known limitations, and how to report a
vulnerability if you find one.

## License

MIT — see `pyproject.toml`.
