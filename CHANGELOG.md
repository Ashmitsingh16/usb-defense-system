# Changelog

## 0.1.4 — 2026-05-21 — PERSIST-1 fix + X11 runbook section

### Bug fixes

- **`usbguard_defense/daemon.py`** — PERSIST-1: persistent lockdown flag now carries the offender dict as JSON instead of the bare string `"active\n"`. `_restore_lockdown_if_needed` parses it on startup and restores `self.lock_offender` so the lockdown overlay shows real device details after a daemon kill / reboot, not `?` placeholders. Backwards-compatible with the 0.1.2/0.1.3 text format (legacy flags trigger lockdown without offender details, which matches the old behaviour).

### Documentation

- **`docs/DEPLOYMENT_RUNBOOK.md` Phase G** — new section documenting the Wayland vs X11 trade-off for the UI and the exact `dnf install` line + `QT_QPA_PLATFORM=xcb` workflow to get real input-grabbing back. Includes a comparison table of overlay behaviour on each platform.

### Verification

- `python -m pytest` → 44 passed, 0 failed.
- `python -m py_compile` clean on `daemon.py`.

---

## 0.1.3 — 2026-05-21 — Live demo capture + Wayland caveat documented

### Known issues observed during live demo capture

- **WAY-1: Wayland input-grab restriction.** Qt5's `grabKeyboard()` / `grabMouse()` on the full-screen lockdown widget are silently ignored on Rocky 9 / GNOME / Wayland (`This plugin supports grabbing the mouse only for popup windows` warning at startup). The overlay still renders, the alarm still sounds, the persistent flag still fires, and the dashboard still shows the locked state, but the operator can switch to other windows. Documented in `docs/REPORT.md` §7.2 as a known weakness with two mitigation paths (X11 fallback via `QT_QPA_PLATFORM=xcb`, or `gtk-layer-shell` `xdg_popup` overlay on Wayland). Not a regression — visible from the very first demo on 2026-05-19, just not labelled as a gap until this session.
- **PERSIST-1: Persistent lockdown flag carries state but not offender details.** After daemon kill / VM reboot, the restored daemon re-enters lockdown but the overlay shows the device fields as `?` until a real event arrives. Fix is a one-liner: serialize the offender dict to the flag file instead of writing the bare string `"active\n"`. Documented in `docs/REPORT.md` §7.2 and queued for §8 future work.

### Live demo evidence captured (2026-05-21)

- Demo 3 — three frames (step 1 lockdown, step 2 `authorized_normal` stays-locked, step 3 `authorized_key` cleared).
- Demo 5 — `Class = HID-Keyboard`, `Hak5 USB Rubber Ducky (simulated)` overlay.
- Demo 4 (re-captured) — post-reboot `SYSTEM LOCKED` overlay with `?` placeholders, proving persistent-flag survival of a host-sleep-induced VM kernel lockup.

All saved under `screenshots/` in the project root.

---

## 0.1.2 — 2026-05-20 — Post-deployment hardening + Demo 3/5 simulator + report draft

### Bug fixes

- **`usbguard_defense/ipc.py`** — `IPCClient._recv_loop` now releases `_sock` in a `finally` block when the loop exits (clean shutdown, EOF, or `OSError`), and `send_command` marks the socket dead on `OSError`. Adds an `is_connected()` accessor so callers don't reach into the private `_sock` attribute. Fixes the "UI thinks daemon is up after `systemctl restart`" desync from yesterday's engineering log (issue #7).
- **`usbguard_defense/daemon.py`** — `status` IPC response is now type-tagged (`"type": "status"`) so the UI's existing event router can dispatch it. Without the tag, the response went through `_on_daemon_event` and was silently ignored.
- **`usbguard_defense/ui/main.py`** — `_refresh_dashboard` reconnects to the daemon on every 2-second tick if disconnected, and hides any stale lockdown overlay on disconnect so a dead daemon cannot pin the operator out of an unlocked workstation. New `status` handler restores the overlay state from the daemon's authoritative response on (re)connect.
- **`usbguard_defense/ui/lockdown.py`** — `show_for` restarts the blink timer; previously `hide_overlay` stopped the timer permanently, so a re-lock would show a non-blinking overlay.

### New features

- **`usbguard_defense/daemon.py`** — `simulate_event` now mirrors the production unlock branch for `authorized_insert` payloads: a simulated authorized USB with `can_unlock=true` clears an active lockdown; one with `can_unlock=false` does not. This makes Demo 3 (asymmetric unlock) reproducible without real hardware.
- **`usbguard_defense/tests/simulate.py`** — added `authorized_normal`, `authorized_key`, `badusb`, and `badusb_lockdown` scenarios. The BadUSB scenario presents `device_class=HID-Keyboard` with an unknown `VID:PID:Serial`, exercising the HID-injection defense path for Demo 5.

### New artifacts

- **`docs/REPORT.md`** — first-pass academic report following `REPORT_OUTLINE.md`, ~20 pages, all 10 sections + 6 appendices. Placeholders left for name/roll-no/guide.
- **`src/usbguard_defense/tests/test_simulate.py`** — 6 new unit tests locking down the scenario dict shape so the demo evidence chain stays intact across future edits.

### Documentation

- **`docs/DEMO_SCENARIOS.md`** — Demo 3 and Demo 5 procedures now lead with the simulator-driven option; the original real-hardware option is kept as "Option B".
- **`WHEN_YOU_RETURN.md`** — re-headed for 2026-05-20 with today's milestones and the simulator commands for capturing the remaining demo evidence.

### Verification

- `python -m pytest` → **44 passed, 0 failed** (38 prior + 6 new in `test_simulate.py`).
- `python -m py_compile` on every edited file → zero errors.

---

## 0.1.0 — 2026-05-18 — Audit pass + testing + packaging

### Bug fixes (all caught during the autonomous code-audit pass)

- **`config/usbguard-rules.conf`** — added explicit HID allow rules so the VM's virtual keyboard and mouse work after the first reboot. Without this, the system would soft-lock the operator out immediately after install.
- **`usbguard_defense/alarm.py`** — switched primary player from `paplay` to `aplay`. The daemon runs as `root` under systemd with no user session, so PulseAudio (per-user service) was unreachable and the alarm would silently fail to play. ALSA `aplay` writes directly to `/dev/snd/*` via the `audio` group.
- **`usbguard_defense/tests/simulate.py`** — was sending event-shaped payloads directly to the IPC server, but the server only routes `cmd`-prefixed messages to its dispatcher. Wrapped the payload as `{"cmd": "simulate_event", "event": …}` so the simulator actually exercises the lockdown flow.
- **`usbguard_defense/daemon.py`** — added a `simulate_event` IPC command that re-broadcasts the wrapped payload (and handles `lockdown_enter` / `lockdown_clear` payloads as real state changes, so the persistent flag and alarm participate too).
- **`usbguard_defense/ui/dashboard.py`** — fixed Qt stylesheet repolish. After a `setObjectName()` change Qt does NOT re-evaluate the stylesheet by default, so the status color never updated after the first paint. Added explicit `style().unpolish(); style().polish(); update()`.
- **`usbguard_defense/monitor.py`** — composite USB devices report `bDeviceClass=00` and put the real class on the interface descriptors. Added fallback parser for `ID_USB_INTERFACES` (format `:CCSSPP:CCSSPP:`) so mass-storage, HID, etc. are reported correctly instead of "InterfaceDefined".
- **`scripts/install.sh`** — added `alsa-utils` to the dnf install line (now that `aplay` is the primary alarm path).
- **`usbguard_defense/ui/event_log.py`** — the "Action" column duplicated the "Type" column's value. Renamed to "Fingerprint" and bound to `ev["fingerprint"]` instead.

### New artifacts

- **`src/pyproject.toml`** — proper Python packaging metadata. Replaces the install script's previous symlink-into-site-packages hack with a clean `pip install -e .` flow. Declares console-script entry points (`usb-defense-daemon`, `usb-defense-ui`, `usb-defense-simulate`).
- **`scripts/install.sh` (Step 4)** — updated to use `pip install -e .` against the new `pyproject.toml`.
- **`src/assets/alarm.wav`** — pre-generated 176 KB / 2-second alternating 600/900 Hz siren. Generated by `scripts/generate_alarm.py` (Python stdlib only — no external deps).
- **38 unit tests** in `src/usbguard_defense/tests/` covering:
  - `test_whitelist.py` — entry construction, load, match, can_unlock, add/remove round-trip, fingerprint-replace semantics
  - `test_config.py` — defaults, YAML overrides, unknown-key tolerance, empty-file fallback
  - `test_event_log.py` — file creation, JSON-line shape, ISO timestamps, malformed-line skipping, read-recent limit
  - `test_usbguard_iface.py` — CLI output line parser (typical allow, block, lowercasing, garbage rejection)
  - All 38 tests pass on Python 3.12 / Windows host.

### New documentation

- **`docs/DEPLOYMENT_RUNBOOK.md`** — click-by-click guide from "open VirtualBox" to "first USB plugged in" (Phases A–F, ~60 min).
- **`docs/DEMO_SCENARIOS.md`** — five scripted demos for the viva (authorized, unauthorized → lockdown, asymmetric unlock, paranoid restart, BadUSB-style HID).
- **`docs/REPORT_OUTLINE.md`** — full academic report skeleton.
- **`docs/SLIDES.md`** — Marp-compatible presentation deck (~15 slides).
- **`docs/VIVA_CHEATSHEET.md`** — printable one-page Q&A.
- **`CHANGELOG.md`** — this file.

### Verification

- `python -m py_compile` on every `.py` file → zero errors.
- `python -m pytest` → 38 passed, 0 failed.

## 0.0.1 — initial — Project scaffold

- VirtualBox 7.2.8 + Extension Pack installed; Rocky-Defense VM pre-created (4 GB / 2 vCPU / 30 GB).
- Rocky Linux 9 DVD ISO downloaded (`ISOs/Rocky-9-latest-x86_64-dvd.iso`, 13.36 GB).
- Initial scaffolding: daemon (`daemon.py`, `monitor.py`, `whitelist.py`, `usbguard_iface.py`, `alarm.py`, `ipc.py`, `event_log.py`, `config.py`).
- PyQt5 UI scaffolding (dashboard, lockdown overlay, whitelist manager, event log, settings, dark theme).
- Initial install/uninstall scripts, systemd service unit, UI autostart `.desktop`.
- Initial docs: `ARCHITECTURE.md`, `LINUX_PRIMER.md`, `INSTALLATION.md`.
