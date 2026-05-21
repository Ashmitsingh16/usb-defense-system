# USB Defense System — Architecture

**Project:** Whitelist-based USB device guard with full system lockdown for Rocky Linux.
**Target:** Indian defense-grade hardened workstation.
**Status:** Student project / academic prototype.

---

## 1. Problem Statement

Unauthorized USB devices are a major attack vector in classified/defense environments:

- **Data exfiltration** — copying secret files onto a thumb drive
- **Malware introduction** — autorun executables, infected documents
- **HID injection (BadUSB)** — a USB pretending to be a keyboard, typing malicious commands silently
- **Network injection** — a USB pretending to be a network adapter, redirecting traffic
- **Stuxnet-style attacks** — entire infrastructure compromised via a single rogue USB

This software defends a Rocky Linux workstation against unauthorized USB connections.

---

## 2. Threat Model

### What we DEFEND AGAINST

| Threat | Defense Mechanism |
|---|---|
| Unauthorized mass storage device plugged in | Whitelist check by VID:PID:Serial; block if not on list |
| Attacker plugs random USB to copy files | System enters lockdown — no input, no display access until authorized USB connects |
| Attacker leaves the workstation, comes back to find it locked | Authorized USB acts as 2FA hardware key — required for unlock |
| Audit / forensics need | All USB events logged with timestamp, device fingerprint, action taken |
| Attacker tries to disable the daemon | systemd auto-restart; tampering logged; daemon-stopped triggers lockdown |
| Attacker reboots and removes the daemon at boot | Daemon installed as enabled-at-boot systemd service; whitelist file is root-owned and append-only |

### What we DO NOT defend against (acknowledged limits)

| Threat | Why we don't defend | Mitigation in real deployment |
|---|---|---|
| BadUSB firmware attacks (USB pretends to be a different device) | Software cannot reliably detect spoofed firmware | Hardware-validated USBs (IronKey, Apricorn) at procurement |
| Attacker has physical access to the disk while system is off | Out of scope for software | Full-disk encryption (LUKS) |
| Attacker has root credentials | Out of scope | Strong access controls, audit, separation of duties |
| Hardware keylogger between keyboard and USB port | Software cannot see this | Physical inspection, tamper-evident enclosures |
| Insider with legitimate authorized USB exfiltrating data | Out of scope (this is HR/policy) | DLP solutions, file-level access auditing |

---

## 3. System Components

```
┌────────────────────────────────────────────────────────────────────┐
│                       USER SPACE (Rocky Linux)                     │
│                                                                    │
│   ┌─────────────────┐    ┌─────────────────────────────────────┐  │
│   │  PyQt5 UI App   │    │       USB Defense Daemon            │  │
│   │   (Dashboard,   │◄──►│      (Python systemd service)       │  │
│   │    Lockdown,    │    │                                     │  │
│   │    Whitelist,   │    │  - Listens to udev USB events       │  │
│   │    Event Log)   │    │  - Looks up whitelist               │  │
│   └────────┬────────┘    │  - Talks to USBGuard via D-Bus      │  │
│            │             │  - Logs to journald                 │  │
│            │             │  - Triggers UI lockdown screen      │  │
│            │             │  - Plays alarm                      │  │
│            │             └──────────────┬──────────────────────┘  │
│            │                            │                         │
│            │ D-Bus / IPC                │ D-Bus                   │
│            ▼                            ▼                         │
│   ┌────────────────────────────────────────────────────────────┐  │
│   │                    USBGuard Daemon                         │  │
│   │           (existing, kernel-level enforcement)             │  │
│   └──────────────────────────┬─────────────────────────────────┘  │
│                              │ syscalls                            │
└──────────────────────────────┼─────────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│                            KERNEL                                  │
│                                                                    │
│   ┌──────────────┐    ┌────────────┐    ┌──────────────────────┐   │
│   │ USB Subsystem│◄──►│   udev     │◄──►│   Authorize/Block    │   │
│   │              │    │  (events)  │    │  (drivers/usb/core)  │   │
│   └──────────────┘    └────────────┘    └──────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

### Component Roles

#### 3.1 USBGuard (existing)
Industry-standard Linux tool. Already installed via `dnf install usbguard`.
- **Why we use it:** Provides kernel-level enforcement (USB devices can be physically blocked from authorizing). Our daemon talks to it via D-Bus rather than re-implementing kernel-level blocking.
- **Configuration:** `/etc/usbguard/usbguard-daemon.conf` and `/etc/usbguard/rules.conf`
- **Default policy we'll set:** `block` everything, then explicitly allow whitelist entries.

#### 3.2 USB Defense Daemon (our code, Python)
- Runs as a systemd service: `usb-defense.service`
- Uses `pyudev` to watch USB insert/remove events independently (don't rely solely on USBGuard for detection — defense in depth)
- Reads whitelist from `/etc/usb-defense/whitelist.json`
- On unauthorized device: triggers UI lockdown, plays alarm, blocks via USBGuard, logs to journald
- On authorized device while in lockdown: unlocks the system

#### 3.3 PyQt5 UI Application (our code, Python)
- Five screens (see below)
- Communicates with daemon via D-Bus (or filesystem socket as fallback)
- Lockdown screen runs on top of all other windows, takes full screen, blocks input

---

## 4. UI Screens

### 4.1 Dashboard (main)
- Status indicator: 🟢 SECURE / 🟡 EVENT (recent unauthorized) / 🔴 LOCKED
- Last event summary
- Currently authorized USBs (shown as cards with VID/PID/serial)
- Quick actions: View Logs, Manage Whitelist, Settings
- Daemon health indicator (running / stopped)

### 4.2 Whitelist Manager
- List of authorized devices
- "Add Device" — prompts user to plug in a USB; reads its VID/PID/Serial; adds to whitelist
- "Remove Device" — removes a device from whitelist
- "Edit Label" — give devices human-readable names ("Admin Backup Drive")
- All operations require admin password

### 4.3 Event Log
- Searchable, filterable list of all USB events
- Columns: Timestamp, Device, Action (allowed/blocked/lockdown), VID:PID:Serial
- Export to CSV for audit reports
- Date range filter

### 4.4 Lockdown Screen
- **Full-screen, always-on-top, blocks all input**
- Big red "SYSTEM LOCKED — UNAUTHORIZED USB DETECTED" banner
- Shows offending device info
- "Insert authorized USB to unlock" prompt
- Visible animated alarm icon
- Sound alarm playing in loop
- Optional: emergency admin override with password (in case authorized USB is lost)

### 4.5 Settings
- Alarm sound choice + volume
- Lockdown sensitivity (immediate / grace period)
- Admin password change
- Notification preferences

---

## 5. Data Flow

### 5.1 USB Insert (allowed device)
```
1. User plugs in authorized USB stick
2. Kernel udev fires "add" event
3. USBGuard daemon receives event, sees USB matches an "allow" rule
4. USBGuard authorizes the device (kernel binds drivers)
5. Our daemon (parallel) sees udev event via pyudev
6. Daemon checks whitelist → device authorized
7. Daemon logs: "AUTHORIZED USB: [details]"
8. Daemon updates UI: dashboard shows green, last event = authorized
9. USB drive auto-mounts at /run/media/user/<label>
10. User can read/write files normally
```

### 5.2 USB Insert (unauthorized device)
```
1. User plugs in unknown USB stick
2. Kernel udev fires "add" event
3. USBGuard sees it doesn't match any allow rule, defaults to BLOCK
4. Kernel prevents device from binding drivers (no /dev/sdb appears)
5. Our daemon sees udev event via pyudev
6. Daemon checks whitelist → NO MATCH
7. Daemon logs: "UNAUTHORIZED USB DETECTED: [details]"
8. Daemon triggers LOCKDOWN:
   a. Spawn fullscreen lockdown UI window (PyQt5)
   b. Start alarm sound loop
   c. Disable input for other apps (window grab)
   d. Optionally lock the screen (loginctl lock-session)
9. System remains in lockdown until authorized USB plugged in
```

### 5.3 Lockdown Unlock (authorized USB plugged in while locked)
```
1. User plugs in authorized USB
2. Daemon sees udev event, looks up whitelist → MATCH
3. Daemon stops alarm, dismisses lockdown UI
4. Daemon logs: "LOCKDOWN CLEARED: [authorized device details]"
5. Dashboard returns to green
6. (Note: the originally offending USB remains physically blocked)
```

### 5.4 Daemon Crash / Tamper
```
1. Daemon process dies for any reason
2. systemd detects exit, restarts within 5 seconds (Restart=always, RestartSec=5)
3. On restart, daemon checks for any "pending unauthorized event" flag in /run/usb-defense/
4. If flag is set, daemon re-enters lockdown mode (paranoid mode)
5. Logs: "DAEMON RESTARTED — possible tampering"
```

---

## 6. File Layout (on Rocky Linux after install)

```
/etc/usb-defense/
  ├── config.yaml            # main settings (alarm volume, sensitivity, etc.)
  ├── whitelist.json         # authorized USB list (root-owned, append-only)
  └── admin.hash             # bcrypt hash of admin password

/usr/local/bin/
  └── usb-defense-ui         # symlink to UI launcher

/usr/lib/usb-defense/
  ├── daemon/                # python source for daemon
  ├── ui/                    # python source for PyQt5 UI
  ├── assets/                # alarm sounds, icons
  └── venv/                  # isolated python virtualenv

/etc/systemd/system/
  └── usb-defense.service    # daemon service file

/var/log/usb-defense/        # custom logs (in addition to journald)
  └── events.log             # append-only event log

/run/usb-defense/            # runtime files (cleared on reboot)
  ├── daemon.pid             # daemon PID
  ├── lockdown.flag          # signals UI to enter lockdown
  └── ipc.sock               # daemon ↔ UI socket
```

---

## 7. Whitelist Format

`/etc/usb-defense/whitelist.json`:

```json
{
  "version": 1,
  "devices": [
    {
      "id": "uuid-1",
      "label": "Admin Backup Drive",
      "vendor_id": "0951",
      "product_id": "1666",
      "serial": "60A44C413FAEE2B129C9015A",
      "device_class": "MassStorage",
      "added_by": "admin",
      "added_at": "2026-05-05T14:32:17Z",
      "can_unlock": true
    },
    {
      "id": "uuid-2",
      "label": "Cybersec Lab USB #3",
      "vendor_id": "0781",
      "product_id": "5567",
      "serial": "4C530001241226119494",
      "device_class": "MassStorage",
      "added_by": "admin",
      "added_at": "2026-05-05T15:00:00Z",
      "can_unlock": false
    }
  ]
}
```

`can_unlock`: only certain "key" USBs can clear a lockdown. Regular authorized USBs are allowed to read/write but can't unlock the system. This separates "trusted data drives" from "unlock keys."

---

## 8. Logging Format

Logs go to **two places**:

### 8.1 systemd journald (queryable, native)
```bash
journalctl -u usb-defense
```

Fields per event (structured logging):
- `TIMESTAMP`, `EVENT_TYPE`, `DEVICE_VID`, `DEVICE_PID`, `DEVICE_SERIAL`, `DEVICE_CLASS`, `USB_VERSION`, `CAPACITY_GB`, `ACTION`, `DAEMON_VERSION`

### 8.2 Append-only flat file `/var/log/usb-defense/events.log`
Tamper-resistant via `chattr +a` (only root can append, no one can edit/delete without removing the attribute first — which itself logs to audit).

Sample line:
```
2026-05-05T14:32:17Z UNAUTHORIZED class=MassStorage vendor=SanDisk(0781) product=Cruzer Blade(5567) serial=4C530001241226119494 usb=3.0 capacity=32GB action=BLOCKED+LOCKDOWN
```

---

## 9. Failure Modes & Defenses

| Scenario | Mitigation |
|---|---|
| Daemon crashes | systemd auto-restart (Restart=always, RestartSec=5) |
| Daemon killed by attacker | Audit log captures kill; /run/usb-defense/lockdown.flag persists; on restart enters lockdown mode |
| Whitelist file modified by attacker | File is root-owned 0600; modifications logged via `auditd`; bcrypt-signed hash check (future hardening) |
| User adds a malicious USB to whitelist | Requires admin password; logged with attribution |
| System rebooted while lockdown was active | lockdown.flag is on disk in /var/lib/usb-defense/, restored on boot |
| Daemon's Python interpreter exploited | Run daemon as dedicated low-privilege user `usbdefense`, with capabilities (CAP_NET_ADMIN if needed) |
| Two USBs plugged simultaneously, one auth one not | Strictest wins — unauthorized triggers lockdown regardless of authorized presence |

---

## 10. Deployment Plan

1. **Stage 1 (now):** Install on Rocky Linux VM, develop locally
2. **Stage 2:** Test with Kali Linux as attacker, demonstrate blocking various USB types
3. **Stage 3:** Run on physical hardened workstation (out of scope for this project)

---

## 11. Out of Scope (for academic version)

- Multi-user enterprise deployment (LDAP/AD integration)
- Centralized event aggregation to SIEM
- Kernel module signing
- Encrypted whitelist + remote attestation
- Mobile companion app for unlock approval
- Integration with hardware security modules (HSM/TPM)

These would be Phase 2 / production hardening.
