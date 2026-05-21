# USB Defense System

Whitelist-based USB device guard with full system lockdown for Rocky Linux.
Designed as a defense-grade hardened workstation security layer.

## What it does

- Watches every USB device that gets plugged in
- Checks against a whitelist of authorized devices (by VID:PID:Serial)
- **Allowed devices** mount normally
- **Unknown devices** trigger:
  - Kernel-level block (via USBGuard) — device cannot bind any drivers
  - Full-screen system lockdown — keyboard/mouse blocked
  - Audible alarm
  - Logged event with full device fingerprint
- **Lockdown clears** only when a whitelisted "unlock key" USB is plugged in

## Quick links

- [Architecture](docs/ARCHITECTURE.md) — system design, threat model, data flow
- [Installation](docs/INSTALLATION.md) — install commands and per-step troubleshooting
- [Deployment Runbook](docs/DEPLOYMENT_RUNBOOK.md) — full click-by-click guide from VirtualBox boot to first USB plug-in
- [Demo Scenarios](docs/DEMO_SCENARIOS.md) — five scripted demos for the viva
- [Report Outline](docs/REPORT_OUTLINE.md) — academic write-up skeleton
- [Presentation Slides](docs/SLIDES.md) — Marp-compatible deck (~15 slides)
- [Viva Cheatsheet](docs/VIVA_CHEATSHEET.md) — printable one-page Q&A
- [Changelog](CHANGELOG.md) — what changed in each iteration
- [Linux Primer](docs/LINUX_PRIMER.md) — beginner Linux reference for this project

## Running the tests

```bash
cd src
pip install pytest PyYAML
python -m pytest usbguard_defense/tests -v
# 38 tests pass — covers whitelist matching, config loading, event log, USBGuard parser
```

## Source layout

```
USB-Defense-Project/
├── src/
│   ├── usbguard_defense/         # Python package
│   │   ├── daemon.py             # main daemon
│   │   ├── monitor.py            # pyudev USB watcher
│   │   ├── whitelist.py          # whitelist management
│   │   ├── usbguard_iface.py     # CLI wrapper for usbguard
│   │   ├── alarm.py              # alarm sound player
│   │   ├── ipc.py                # daemon ↔ UI socket
│   │   ├── event_log.py          # append-only flat-file log
│   │   ├── config.py             # config loading
│   │   └── ui/                   # PyQt5 UI
│   │       ├── main.py
│   │       ├── dashboard.py
│   │       ├── lockdown.py       # full-screen overlay
│   │       ├── whitelist_mgr.py
│   │       ├── event_log.py
│   │       ├── settings.py
│   │       └── styles.py
│   ├── config/                   # default config files
│   ├── systemd/                  # systemd service unit + UI autostart
│   ├── scripts/                  # install.sh, uninstall.sh
│   ├── assets/                   # alarm.wav (provide separately)
│   └── requirements.txt
├── docs/
├── ISOs/                         # downloaded Rocky Linux ISO
├── VMs/                          # VirtualBox VM files
└── Downloads/                    # VirtualBox installers etc.
```

## Install on Rocky Linux 9

```bash
cd USB-Defense-Project/src
sudo ./scripts/install.sh
```

## Run

```bash
# Start the daemon (auto-starts on boot after install)
sudo systemctl start usb-defense

# Check status
sudo systemctl status usb-defense

# Open the UI
usb-defense-py -m usbguard_defense.ui.main
```

## Components

| Layer | Tech |
|---|---|
| OS | Rocky Linux 9 |
| Kernel enforcement | USBGuard |
| Daemon | Python 3 + pyudev |
| UI | PyQt5 (dark theme) |
| IPC | Unix socket + line-delimited JSON |
| Logging | journald + append-only flat file |
| Service mgmt | systemd |

## Status

- [x] VirtualBox 7.2.8 + Extension Pack installed
- [x] `Rocky-Defense` VM pre-created (4 GB RAM, 2 vCPU, 30 GB disk, xHCI USB)
- [x] Rocky Linux 9 DVD ISO downloaded (`ISOs/Rocky-9-latest-x86_64-dvd.iso`)
- [x] Architecture, Linux primer, and installation guide written
- [x] Daemon scaffolded, audited, and bug-fixed (boot-lockout, alarm, simulator, dashboard repolish, device-class fallback)
- [x] PyQt5 UI scaffolded and bug-fixed
- [x] Install/uninstall scripts + systemd unit + autostart `.desktop`
- [x] `alarm.wav` generated and bundled at `src/assets/alarm.wav`
- [x] All Python files compile-checked (zero errors)
- [x] **38 unit tests** for the pure-Python core — all passing
- [x] `pyproject.toml` for proper `pip install -e .` packaging
- [x] Example populated whitelist (`src/config/whitelist.example.json`)
- [x] Deployment runbook, demo scenarios, report outline, slides, viva cheatsheet, changelog written
- [ ] Boot Rocky inside the VM and run `install.sh` (interactive — see `docs/DEPLOYMENT_RUNBOOK.md`)
- [ ] First end-to-end USB test inside Rocky Linux VM
- [ ] BadUSB demonstration / Kali attack scenarios
- [ ] Final report draft
