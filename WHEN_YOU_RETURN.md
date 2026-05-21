# Where the project is, right now

**Updated 2026-05-21** — all 5 demos captured, two honest caveats added to the report (Wayland input-grab, persistent-flag placeholders).

## Today's milestones (2026-05-21)

- ✅ Recovered the VM after an overnight host-sleep kernel soft-lockup (CPU#0 stuck 15660s). `Machine → Reset` brought it back.
- ✅ **Demo 4 re-captured for free** — on reboot, the daemon read `/var/lib/usb-defense/lockdown.flag` and re-entered lockdown with no fresh USB event. Screenshot saved (`?` placeholders in offender fields — known issue PERSIST-1, documented).
- ✅ Re-synced today's code into `/usr/lib/usb-defense/` via rsync from `/media/sf_USB-Defense-Project/` (the actual shared-folder mount; not `/mnt/usb-defense-project` as the old WHEN_YOU_RETURN claimed).
- ✅ **Demo 3 captured end-to-end** with the new simulator: `lockdown` → `authorized_normal` (stays locked) → `authorized_key` (clears). Three screenshots.
- ✅ **Demo 5 captured**: `badusb_lockdown` shows `Class = HID-Keyboard`, `Hak5 USB Rubber Ducky (simulated)`. One screenshot.
- ✅ **Two honest caveats added** to `docs/REPORT.md` §7.2 + `CHANGELOG.md`:
  - **WAY-1**: Wayland silently no-ops `grabKeyboard`/`grabMouse` on regular windows. Overlay renders but doesn't grab. Mitigations documented (X11 fallback or `gtk-layer-shell` popup).
  - **PERSIST-1**: Persistent flag carries `locked=True` but not offender details. Trivial one-line fix queued for future work.

## Screenshots collected

Live in `C:\Users\KIIT\Pictures\Screenshots\`. Move them to `screenshots/` in the project folder and rename:

| Source filename | Rename to |
|---|---|
| 2026-05-19 015645 (or similar with green dashboard + "allowed: Admin Backup Drive") | `demo1_authorized_allowed.png` |
| 2026-05-19 015823 (red SYSTEM LOCKED, real device) | `demo2_unauthorized_locked.png` |
| 2026-05-19 020404 (journalctl showing `Found persistent lockdown flag`) | `demo4_persistent_flag_old.png` |
| 2026-05-21 093655 (post-reboot lockdown with `?` placeholders) | `demo4_persistent_flag_restored.png` |
| 2026-05-21 094950 (Sketchy Stick MassStorage overlay) | `demo3_step1_locked.png` |
| 2026-05-21 094956 or next one (overlay still up after authorized_normal) | `demo3_step2_normal_stays_locked.png` |
| 2026-05-21 0950xx (green dashboard) | `demo3_step3_unlocked.png` |
| 2026-05-21 095359 (Hak5 Rubber Ducky HID-Keyboard overlay) | `demo5_badusb_locked.png` |

## Late-afternoon polish (also 2026-05-21)

- ✅ **PERSIST-1 fixed in 0.1.4.** `daemon.py` now writes the offender as a JSON dict to `/var/lib/usb-defense/lockdown.flag` and restores it on startup. The `?` placeholders are gone for any new lockdown. Backwards-compatible with the old text-format flag. 44 tests still pass.
- ✅ **X11 fallback documented.** `docs/DEPLOYMENT_RUNBOOK.md` Phase G is new: comparison table for Wayland vs X11 behaviour, exact `dnf install` line for the X11 backend libs, and the `QT_QPA_PLATFORM=xcb` workflow. If you want a stronger Demo 2, follow Phase G to switch to GNOME-on-Xorg.
- ✅ `docs/REPORT.md` §7.2 updated: PERSIST-1 is now described as "resolved in 0.1.4" rather than "future work".

## What's left

- **Fill in the report placeholders** — name, roll no, guide, institute, date — in `docs/REPORT.md` title page (line ~14).
- **Insert figure references** — Appendix D currently lists 6 figures; once the screenshots are renamed and copied, write `![Demo 3 step 1](screenshots/demo3_step1_locked.png)` in the body where each figure is mentioned, or just attach the PNGs as figures in your final Word/PDF compile.
- **Optionally re-sync code to the VM** to pick up the PERSIST-1 fix: from inside the VM, `sudo rsync -av /media/sf_USB-Defense-Project/src/usbguard_defense/ /usr/lib/usb-defense/usbguard_defense/ && sudo systemctl restart usb-defense`. Then re-trigger Demo 4 and you'll see the overlay populated with actual device details instead of `?`.
- **Render the slides** — `marp docs/SLIDES.md -o slides.pdf` (needs `npm i -g @marp-team/marp-cli`).
- **Show your senior** — `WHEN_YOU_RETURN.md` + `REPORT.md` + `screenshots/` + `SLIDES.md` is enough.

## Previous milestones (2026-05-20)

## Today's milestones (2026-05-20)

- ✅ **UI desync bug fixed** (issue #7 from yesterday). Three coordinated changes:
  - `ipc.py`: `IPCClient._recv_loop` now releases `_sock` on disconnect via a `finally` block; `send_command` marks the socket dead on `OSError`.
  - `daemon.py`: `status` response is now `type`-tagged so the UI can route it.
  - `ui/main.py`: `_refresh_dashboard` reconnects on every tick if disconnected and hides any stale overlay; new `status` handler syncs the overlay to the daemon's authoritative state on (re)connect.
  - `ui/lockdown.py`: `show_for` restarts the blink timer (was permanently stopped by `hide_overlay`).
- ✅ **Demo 3 simulator added** — `authorized_normal` (can_unlock=false) and `authorized_key` (can_unlock=true) scenarios in `tests/simulate.py`. Daemon's `simulate_event` handler now mirrors the production unlock logic for `authorized_insert` so the asymmetric-unlock demo runs end-to-end without real hardware.
- ✅ **Demo 5 simulator added** — `badusb` (HID-Keyboard class, unknown VID:PID) and `badusb_lockdown` scenarios. `DEMO_SCENARIOS.md` updated with the new commands.
- ✅ **`test_simulate.py` added** — 6 new tests locking down the scenario dict shape (e.g. `authorized_normal` must have `can_unlock=False`). Total test count now **44 passing**.
- ✅ **`docs/REPORT.md` first-pass drafted** — ~20 page academic report following `REPORT_OUTLINE.md`, all 10 sections + 6 appendices. Placeholders left for name/roll-no/guide. Screenshots from yesterday referenced as figures 1–6. Ready to read end-to-end and tighten.

## Files changed today

```
src/usbguard_defense/ipc.py                       (reconnect-aware client)
src/usbguard_defense/daemon.py                    (status type-tag + sim unlock)
src/usbguard_defense/ui/main.py                   (reconnect + status sync)
src/usbguard_defense/ui/lockdown.py               (blink-timer restart)
src/usbguard_defense/tests/simulate.py            (new scenarios)
src/usbguard_defense/tests/test_simulate.py       (NEW)
docs/DEMO_SCENARIOS.md                            (Demo 3+5 simulator paths)
docs/REPORT.md                                    (NEW — first-pass report)
```

## How to capture the remaining Demo 3 & Demo 5 evidence

You can do this on the VM in ~5 minutes — no real USB needed:

```bash
# In Rocky, one terminal: tail the log
sudo journalctl -u usb-defense -f

# In a second terminal: run the simulator with screenshots open
sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate lockdown
# → overlay appears; screenshot for "lockdown raised"

sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate authorized_normal
# → log shows authorized_insert, overlay STAYS; screenshot proving asymmetry

sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate authorized_key
# → log shows "Lockdown cleared", overlay hides; screenshot for "unlock-key cleared lockdown"

sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate badusb_lockdown
# → overlay appears with device_class=HID-Keyboard; screenshot for Demo 5
```

That gets you Demos 3 and 5 in the can without borrowing a Rubber Ducky.

## Previous milestones (2026-05-19)

- ✅ Rocky Linux 9.7 installed in the VM (after fresh-disk recovery from initial install bug)
- ✅ User `ashmit` / `1353` created, sudo configured (had to add to wheel group manually)
- ✅ Guest Additions installed → shared folder mounted at `/mnt/usb-defense-project`
- ✅ `scripts/install.sh` completed all 8 steps (after fixing the USBGuard rules-file syntax)
- ✅ Daemon running as systemd service (`active (running)`)
- ✅ PyQt5 GUI launches and connects to daemon (status bar: "Connected to daemon")
- ✅ **Demo 1 — Authorized USB allowed** (screenshot: dashboard with "allowed: Admin Backup Drive")
- ✅ **Demo 2 — Unauthorized USB triggers lockdown** (screenshot: red SYSTEM LOCKED overlay)
- ✅ **Demo 4 — Paranoid restart resilience** (journalctl log: "Found persistent lockdown flag — entering lockdown on startup" after SIGKILL)
- ✅ **VirtualBox snapshot `post-install-working`** taken — safe rewind point. UUID `aa629566-ecd6-4b33-b2f5-6f1be938b7bf`

## Issues found & fixed today (for the report's "Engineering log" section)

1. `usbguard-rules.conf` — original syntax with `equals { ... }` and `one-of { ... }` operators wasn't parsed by Rocky 9's USBGuard. Replaced with simple `with-interface <class>` single-value form. Source file fixed.
2. User created during Rocky install didn't get sudo — fixed manually via `usermod -aG wheel ashmit`.
3. `usb-defense-py` symlink broke venv auto-detection so PyQt5 wasn't on import path. Workaround: invoke `/usr/lib/usb-defense/venv/bin/python` directly, set `PYTHONPATH=/usr/lib/usb-defense`.
4. Permissions on `/usr/lib/usb-defense/usbguard_defense/` and `/etc/usb-defense/*` blocked the non-root UI. Opened with `chmod -R a+rX`.
5. IPC socket was `0660` (root-only) but UI runs as user — changed to `0666` in `ipc.py`. Source file fixed.
6. Qt couldn't load xcb platform plugin on Rocky 9. Worked around with `export QT_QPA_PLATFORM=wayland`. (xcb-util-cursor install alone didn't fix it; needs additional libs.)
7. UI state can desync from daemon if daemon dies while UI is connected — lockdown overlay stuck after a daemon restart. Workaround: `pkill -f usbguard_defense.ui.main` + relaunch. To-do: have UI poll daemon `status` on reconnect.
8. Live snapshot got stuck in `livesnapshotting` state for 4+ hours — had to force power-off + offline snapshot instead. Lesson: always do offline snapshots for this VM (RAM dump is slow).

## How to reconnect tomorrow

1. Open VirtualBox → double-click **Rocky-Defense** → wait for desktop.
2. Log in as `ashmit` / `1353`.
3. Open Terminal in Rocky.
4. Launch the UI:
   ```
   cd /usr/lib/usb-defense
   export QT_QPA_PLATFORM=wayland
   ./venv/bin/python -m usbguard_defense.ui.main
   ```
5. On Windows: open a terminal/PowerShell, `cd C:\Users\KIIT\Desktop\USB-Defense-Project`, run `claude`.
6. Type "I'm back from yesterday, continue."

## What's still to do

- **Demo 3** (asymmetric unlock: can_unlock=true vs false) — needs real USB hardware or improved simulator
- **Demo 5** (BadUSB / HID-injection scenario) — needs real USB Rubber Ducky or the in-process simulation
- **Real USB plug-in test** — actually pass a USB stick from Windows through to Rocky via VirtualBox's USB passthrough
- **Write the report** — use `docs/REPORT_OUTLINE.md` as skeleton, screenshots from today as evidence
- **Render slides to PDF** — `marp docs/SLIDES.md -o slides.pdf` (needs `npm i -g @marp-team/marp-cli`)
- **Show senior** — `docs/WHEN_YOU_RETURN.md` + `docs/SLIDES.md` + screenshots are enough to demonstrate progress
- **Improve UI desync** — make UI query daemon `status` on reconnect so it can show/hide overlay correctly

## Quick restore from snapshot if anything breaks

VirtualBox Manager → right-click **Rocky-Defense** → **Snapshots** → right-click `post-install-working` → **Restore** → confirm. 30 seconds, you're back to exactly today's working state.

---



## What's complete

### Phase 1 — VM and ISO (✅)
- VirtualBox 7.2.8 + Extension Pack installed.
- `Rocky-Defense` VM pre-created: 4 GB RAM, 2 vCPU, 30 GB disk, xHCI USB 3.0, NAT network, bidirectional clipboard.
- Rocky Linux 9 DVD ISO at `ISOs/Rocky-9-latest-x86_64-dvd.iso` (13.36 GB, fully downloaded).

### Phase 2 — Documentation (✅)
In `docs/`:
- `ARCHITECTURE.md` — system design, threat model, data flow, file layout, failure modes.
- `LINUX_PRIMER.md` — beginner Linux reference.
- `INSTALLATION.md` — installer commands + troubleshooting.
- `DEPLOYMENT_RUNBOOK.md` — click-by-click guide from "open VirtualBox" through "first USB plugged in". Follow this when you sit down.
- `DEMO_SCENARIOS.md` — five scripted demos for your viva (authorized USB allowed, unauthorized USB locks, unlock key clears, paranoid restart resilience, BadUSB HID scenario).
- `REPORT_OUTLINE.md` — academic report skeleton with every section and what to put in it.
- **`SLIDES.md`** — Marp-compatible presentation deck (~15 slides). Render: `marp docs/SLIDES.md -o slides.pdf` (after `npm i -g @marp-team/marp-cli`).
- **`VIVA_CHEATSHEET.md`** — printable one-page Q&A. Print this, bring it.
- **`CHANGELOG.md`** at repo root — what changed when.

### Phase 3 — Project code (✅ scaffolded AND audited)
Located at `src/usbguard_defense/`.

**Daemon:** `daemon.py`, `monitor.py`, `whitelist.py`, `usbguard_iface.py`, `alarm.py`, `ipc.py`, `event_log.py`, `config.py`.

**PyQt5 UI:** `ui/main.py`, `ui/dashboard.py`, `ui/lockdown.py`, `ui/whitelist_mgr.py`, `ui/event_log.py`, `ui/settings.py`, `ui/styles.py`.

**Test/simulator:** `tests/simulate.py` (now correctly triggers UI lockdown via daemon).

**Configs:** `config/config.yaml`, `config/whitelist.json` (empty starter), `config/whitelist.example.json` (NEW — 4 example entries showing the schema), `config/usbguard-rules.conf` (safe — doesn't lock out VM keyboard).

**Deployment:** `scripts/install.sh`, `scripts/uninstall.sh`, `scripts/generate_alarm.py`, `scripts/run_dev.sh`, `systemd/usb-defense.service`, `systemd/usb-defense-ui.desktop`, `requirements.txt`.

**Bundled asset:** `src/assets/alarm.wav` — already generated (176 KB, 2-second siren).

**Packaging:** `src/pyproject.toml` — proper Python packaging metadata. Install script uses `pip install -e .` instead of the previous symlink hack.

**Tests:** `src/usbguard_defense/tests/test_{whitelist,config,event_log,usbguard_iface}.py` — **38 unit tests, all passing**. Covers whitelist match logic (including the security-critical "wrong serial = no match" case), config loading, event-log JSON shape, USBGuard CLI parser. Run with: `cd src && python -m pytest usbguard_defense/tests -v`.

### Phase 4 — Code audit pass (✅ done this session)
Fixed the caveats that were in the earlier note:
- `usbguard-rules.conf` — added HID allow rules so the VM's keyboard works after install.
- `alarm.py` — switched from `paplay` (user-session-bound) to `aplay` (works as root daemon). Falls back to `paplay` if needed.
- `tests/simulate.py` — was a no-op against the lockdown UI; now wraps payload as a daemon command and the daemon broadcasts to all UI clients.
- `daemon.py` — added `simulate_event` IPC command.
- `ui/dashboard.py` — fixed Qt stylesheet repolish so status color actually changes when state changes.
- `monitor.py` — added fallback to `ID_USB_INTERFACES` when `bDeviceClass=00` (composite devices).
- `install.sh` — added `alsa-utils` to the dnf install line.
- `ui/event_log.py` — fixed duplicated "Action" column.
- All 19 Python files compile-check clean (`python -m py_compile`).

## What's NOT done — and why

Each of these needs **your hands** because they involve booting the VM, installing an OS interactively, or plugging real hardware. Step-by-step instructions for all of them are in `docs/DEPLOYMENT_RUNBOOK.md`.

1. **Boot Rocky in the VM and install it** (~30 min, mostly waiting). Runbook Phase A + B.
2. **Update Rocky + install Guest Additions + set up shared folder** (~10 min). Runbook Phase C.
3. **Run `sudo ./scripts/install.sh`** inside Rocky (~5 min). Runbook Phase D.
4. **Verify with the simulator + plug a real USB** (~10 min). Runbook Phase E.
5. **Take a snapshot** (1 min). Runbook Phase F. Do this before any further changes.
6. **Run the five demos** for your report — see `docs/DEMO_SCENARIOS.md`.
7. **Write the report** using `docs/REPORT_OUTLINE.md` as the skeleton.

## What you should do, in order

1. Open `docs/DEPLOYMENT_RUNBOOK.md` and follow Phase A → F. ~60 minutes start-to-finish.
2. Take the snapshot.
3. Run Demo 1 from `docs/DEMO_SCENARIOS.md` to confirm the happy path.
4. Run Demos 2–5 and capture screenshots for the report.
5. Open `docs/REPORT_OUTLINE.md` and start filling in sections in order.

If anything in the runbook fails, tell me which step number + what the error said, and I'll diagnose.

## Things to decide / discuss with your senior

1. **Reduce from 5 VMs to 3.** Show them this file + `docs/ARCHITECTURE.md`. Justifies a tighter scope: Rocky-Defense (target) + Kali (attacker) is enough for the demos.
2. **Alarm tone.** The bundled `alarm.wav` is a 2-second 600/900 Hz alternating siren. We can swap it for something scarier (longer, layered, recorded) before the viva.
3. **Unlock-key strategy.** Current default: only USBs marked `can_unlock=true` clear a lockdown. Regular authorized USBs are read/write only. Talk this through — it's the most "design judgment" decision in the project.
4. **Real BadUSB hardware.** For Demo 5, real Rubber Ducky beats a software simulation. If you can borrow one, do.

## Honest caveats that still stand

- Code has been compile-checked on Windows but not yet executed end-to-end on Linux. First run will likely surface one or two runtime issues — that's normal. We'll fix them together when you hit them.
- Lockdown overlay uses Qt's `grabKeyboard`/`grabMouse`. Bypassable by switching to a TTY (`Ctrl+Alt+F3`). Documented in `docs/REPORT_OUTLINE.md` §7.2 as a known weakness.
- Append-only event log uses `chattr +a` which only works on ext4. Rocky 9's default is ext4 (root fs), so we're fine on the target.
- USBGuard's deny-by-default rule means: if you somehow lose your authorized USB AND the VM has no working keyboard, you're locked out. The HID allow rule in `usbguard-rules.conf` prevents this in the VM, but on a real hardened workstation you'd want to enroll your keyboards explicitly.
