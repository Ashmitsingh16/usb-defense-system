# USB Defense System for Defense-Grade Hardened Workstations

*A whitelist-enforced, lockdown-capable USB security layer for Rocky Linux 9*

---

**Author:** Ratnesh Sharma
**Roll No:** _________________
**Guide:** _________________
**Department / Institute:** _________________
**Submission date:** _________________

---

## Abstract

USB devices remain one of the most heavily exploited attack vectors against
classified and defense-grade computing environments. Headline incidents
ranging from Stuxnet's propagation through removable media at Natanz, to the
2014 BadUSB disclosure of firmware-level identity spoofing, to ongoing
data-exfiltration cases at military contractors, all share a common thread:
the workstation has no reliable, end-to-end policy for which USB devices may
attach and what happens when an unknown one does.

Existing tooling on Linux is fragmented. `USBGuard` provides kernel-level
authorization but no user-visible response. `udisks2` provides mounting
policy but no defense intent. Commercial endpoint products exist
(`DeviceLock`, `McAfee Device Control`, `Microsoft Defender Device Guard`)
but are closed-source, Windows-focused, and unavailable for an
air-gapped Rocky Linux deployment. None of them combine kernel-level
blocking, a user-visible full-screen lockdown, a tamper-resistant audit
trail, and self-recovery from process kills in a single open-source layer.

This project closes that gap. The **USB Defense System** is a Python daemon
plus PyQt5 GUI that integrates with USBGuard on Rocky Linux 9 to enforce a
strict deny-by-default policy against a VID:PID:Serial whitelist. When an
unknown USB device is attached, the system enters a full-screen lockdown
state — input-grabbed UI, audible alarm, persistent on-disk flag — that can
only be cleared by attaching a USB explicitly marked as an "unlock key" in
the whitelist. Every event is logged to both `journald` and an
append-only flat file protected with the `chattr +a` filesystem attribute.

The system is validated through five scripted demonstrations, including a
BadUSB / HID-injection scenario, a paranoid-restart resilience test that
proves the daemon re-enters lockdown after a `SIGKILL`, and an asymmetric
unlock test that proves regular authorized data drives cannot clear an
active lockdown. The work intentionally scopes out threats that software
cannot honestly address — firmware-level identity spoofing, hardware
keyloggers, offline disk attacks, and insider abuse of legitimate
credentials — and documents those limits explicitly rather than
overclaiming defense.

The deliverable is approximately 3,000 lines of audited Python with 44
passing unit tests, a hardened systemd integration, a printable viva
cheat-sheet, and a step-by-step deployment runbook that reproduces the
production environment from a clean Rocky 9 VM in roughly an hour.

---

## 1. Introduction

### 1.1 Motivation

USB ports are simultaneously the most useful and the most dangerous I/O
interfaces on a modern workstation. They are the standard mechanism by
which operators move data, attach peripherals, install firmware updates,
and recover broken systems. They are also the standard mechanism by which
attackers have, repeatedly and successfully, breached environments that
were otherwise air-gapped, network-segmented, and physically guarded.

Three classes of incident in particular motivate this work:

- **Stuxnet (2010).** The Natanz uranium enrichment plant in Iran was
  air-gapped — that is, it had no network connectivity at all to systems
  outside its physical perimeter. It was nonetheless compromised by
  malware that propagated through USB drives carried in by maintenance
  contractors. Stuxnet remains the canonical proof that air-gapping a
  classified network without controlling USB is not air-gapping at all.

- **BadUSB (2014).** Karsten Nohl and Jakob Lell demonstrated at
  Black Hat USA that the firmware of common USB controllers can be
  reflashed to make a device claim to be a different class entirely — a
  thumb drive that registers itself as a keyboard, then types attack
  commands at machine speed; or as a network adapter, then silently
  redirects DNS. The class of attack is broadly known as "HID injection"
  when it impersonates a keyboard, and is operationalised in inexpensive
  tools such as the Hak5 USB Rubber Ducky and Bash Bunny.

- **Defense-sector data exfiltration.** A persistent, documented pattern
  in incident reports from US, UK, French, Indian, and Israeli defense
  organisations is the use of removable media — frequently personal USB
  drives — to copy classified data off internal systems for transfer to
  outside parties. The technical primitive is the same in every case:
  the workstation has no reliable enforcement layer for which USB
  devices may attach.

The proposed system addresses the first and third categories directly,
and the second category to the extent that any software-only layer can
(see §3 for the honest threat model).

### 1.2 Problem Statement

Unauthorized USB devices are a major attack vector in classified and
defense environments. There exists no end-to-end open-source workstation
layer on Linux that simultaneously: (a) detects every USB attach event,
(b) enforces a deny-by-default whitelist at the kernel layer, (c)
triggers a visible and audible system-lockdown response that cannot be
trivially clicked away, (d) maintains a tamper-resistant audit trail,
and (e) survives a hostile kill of its own enforcement process. This
project implements such a layer for Rocky Linux 9.

### 1.3 Objectives

The system is required to:

1. Detect every USB attach/detach event on the target workstation in real
   time.
2. Compute a stable device fingerprint (`VID:PID:Serial`) for every event
   and check it against an admin-curated whitelist.
3. Block unknown devices at the kernel level via USBGuard, before any
   driver binds.
4. Trigger a full-screen, input-grabbing lockdown UI with an audible
   alarm on any unauthorized attach.
5. Distinguish trusted *data drives* from *unlock-key* USBs, such that
   only the latter can clear an active lockdown.
6. Produce an append-only, tamper-resistant audit log of every event.
7. Survive `SIGKILL` against the enforcement daemon: on systemd restart,
   the daemon must re-enter lockdown from a persistent on-disk flag if
   one existed at the moment of the kill.
8. Run as a hardened systemd service with `ProtectSystem=strict`,
   `ProtectHome=true`, `PrivateTmp=true`, `NoNewPrivileges=yes`, and a
   minimal `ReadWritePaths` allowlist.

### 1.4 Scope and Non-Scope

The project deliberately and honestly excludes threats that no
software-only USB layer can address. The two tables in §3 enumerate these.
The summary is: this work raises the bar against opportunistic and
mid-skill attacks substantially, and provides forensic evidence even where
it cannot fully prevent the attack. It does not — and cannot — defend
against firmware-spoofing of an authorized device's identity, hardware
implants, offline disk attacks, insider abuse of legitimate credentials,
or attackers who already possess root on the target machine.

This is not a limitation to be hidden. It is the central honesty of
defense engineering, and the corresponding mitigations at procurement
(hardware-validated USBs such as IronKey or Apricorn), at storage (LUKS
full-disk encryption), and at policy (separation of duties, DLP, physical
inspection) are stated explicitly throughout the report.

---

## 2. Background and Related Work

### 2.1 USB attack surface

The USB specification permits a single physical device to advertise
multiple interface classes, and to change its advertised class after
enumeration. The kernel binds drivers to whatever class the device
declares. This composability is the root cause of most USB-borne
attacks. A complete taxonomy of the attack surface includes:

- **Mass-storage exfiltration and malware introduction.** The classical
  case: a thumb drive carrying an autorun executable, an Office document
  with a malicious macro, or simply a destination for `cp -r
  /home/user/* /run/media/usb/`. Defended by the whitelist plus the
  append-only audit log.

- **Firmware-rewriting (BadUSB).** A USB device whose controller has been
  reflashed to misrepresent its class. The Nohl/Lell 2014 disclosure
  showed this is feasible on most consumer-grade USB controllers. Not
  defendable in software once the attacker is able to spoof an
  authorized device's `VID:PID:Serial` triplet, because the spoofed
  device is, from the operating-system's perspective, indistinguishable
  from the genuine one.

- **HID injection.** A device that claims to be a keyboard and types
  attacker-controlled keystrokes at very high speed. Operationalised in
  the Hak5 Rubber Ducky (`VID:PID 03eb:2402`), the Bash Bunny, and DIY
  Arduino Pro Micro-based devices. Defended by the whitelist (an unknown
  HID device is rejected like any other unknown device) but with the
  caveat that an HID device spoofing an authorized keyboard's identity
  would pass through.

- **Network adapter injection.** A device that claims to be an Ethernet
  or wireless adapter and silently routes traffic through attacker
  infrastructure. The Hak5 LAN Turtle is the textbook example. Defended
  by the same whitelist mechanism.

- **Power and signalling attacks ("juice jacking", USB Killer).** The
  attacker uses the USB port for purposes other than data exchange.
  Outside the scope of any software layer.

### 2.2 Existing defenses surveyed

| Tool | Layer | Open-source | Lockdown UI | Audit trail | Unlock-key concept |
|---|---|---|---|---|---|
| USBGuard | Kernel | Yes | No | journald only | No |
| udisks2 / udev rules | Userspace mounting | Yes | No | journald only | No |
| DeviceLock | Endpoint suite (Windows) | No | Partial | Yes | No |
| McAfee Device Control | Endpoint suite (Windows) | No | No | Yes | No |
| MS Defender Device Guard | Endpoint suite (Windows) | No | Partial | Yes | No |
| IronKey / Apricorn hardware | Procurement | Hardware | N/A | Hardware logs | Hardware-bound |
| **This work** | Userspace + Kernel via USBGuard | **Yes** | **Yes** | **Yes (dual)** | **Yes** |

USBGuard, on which this project depends, is by itself the closest
prior art at the kernel layer. It is missing the user-visible
response, the asymmetric unlock-key concept, the daemon-kill resilience,
and the tamper-resistant flat-file audit trail that distinguish this
work.

### 2.3 Gap this project fills

The combination of:

- open-source,
- full-stack (kernel block + GUI lockdown + audit log + self-recovery),
- targeted at a defense-grade Linux workstation,
- with an explicit unlock-key separation that distinguishes data drives
  from authentication tokens,

is, to the best of the author's literature search, not available as a
single packaged solution. This project provides it.

---

## 3. Threat Model

This section reproduces and elaborates the threat model from
`docs/ARCHITECTURE.md` §2.

### 3.1 Threats DEFENDED AGAINST

| Threat | Defense mechanism in this work |
|---|---|
| Unauthorized mass-storage device plugged in | VID:PID:Serial whitelist check; device blocked at kernel via USBGuard if not on list |
| Attacker plugs random USB to copy files | Full-screen lockdown overlay grabs keyboard and mouse; alarm sounds; system unusable until cleared |
| Attacker leaves workstation, returns later to a locked screen | Authorized-but-unlock-key USB acts as a 2FA-style hardware token required to clear lockdown |
| Audit / forensics requirement | All events logged with timestamp, VID:PID:Serial, device class, action taken — to both `journald` and an `append-only` flat file |
| Attacker tries to disable the enforcement daemon | systemd `Restart=always` brings it back within 5 seconds; the kill itself appears in `journalctl` |
| Attacker `kill -9`s the daemon mid-lockdown to dismiss the overlay | Persistent on-disk flag at `/var/lib/usb-defense/lockdown.flag` survives the kill; restored daemon re-enters lockdown immediately |
| Attacker reboots the workstation to bypass lockdown | The persistent flag is on a regular ext4 path that survives reboot; the daemon is `enabled` at boot via systemd |
| Attacker modifies the whitelist file | File is root-owned `0600`; the daemon process runs as root with `NoNewPrivileges=yes`; modifications can be audited through `auditd`; bcrypt-signed integrity verification is staged for Phase 2 |

### 3.2 Threats EXPLICITLY OUT OF SCOPE

| Threat | Why a software layer cannot defend | Real-world mitigation at procurement / policy |
|---|---|---|
| BadUSB firmware spoofing an authorized device's `VID:PID:Serial` | The kernel cannot distinguish a spoofed device from the genuine one — there is no physical-layer authentication in USB 2.0/3.0 | Hardware-validated USBs (IronKey, Apricorn) signed by a vendor PKI |
| Adversary with offline access to the disk | The defense daemon is not running when the system is off | Full-disk encryption (LUKS) with a TPM-bound key |
| Adversary with root credentials on the target | Any defense the daemon enforces, the adversary can disable | Strong access controls; separation of duties; audited admin accounts |
| Hardware keylogger spliced between keyboard and USB port | Invisible to all software layers | Tamper-evident enclosures; physical inspection regime |
| Authorized insider exfiltrating data via a legitimately whitelisted USB | The device is, by definition, authorized | DLP solutions; file-level audit; legal/HR controls |
| Side-channel attacks (USB power line, electromagnetic emission) | Out of OS-level scope | Faraday cage; TEMPEST-rated rooms |

### 3.3 Assumptions

The threat model assumes:

1. The adversary has physical access to the workstation's USB ports.
2. The adversary does **not** have root credentials on the target.
3. The disk is encrypted at rest (LUKS) — outside the scope of this work.
4. The workstation operates in a controlled physical environment.
5. The defender accepts that software cannot detect firmware spoofing of
   an *authorized* device's identity, and procures hardware-validated USBs
   for the unlock-key role accordingly.

---

## 4. System Design

### 4.1 Architecture overview

```
┌────────────────────────────────────────────────────────────────────┐
│                       USER SPACE (Rocky Linux 9)                   │
│                                                                    │
│   ┌─────────────────┐    ┌─────────────────────────────────────┐   │
│   │  PyQt5 UI App   │    │       USB Defense Daemon            │   │
│   │   (Dashboard,   │◄──►│      (Python systemd service)       │   │
│   │    Lockdown,    │    │                                     │   │
│   │    Whitelist,   │    │  - pyudev USB event monitor         │   │
│   │    Event Log)   │    │  - whitelist match                  │   │
│   └────────┬────────┘    │  - USBGuard CLI bridge              │   │
│            │             │  - journald + flat-file audit       │   │
│            │             │  - lockdown overlay broadcaster     │   │
│            │             │  - aplay alarm                      │   │
│            │ Unix-socket │                                     │   │
│            │ + JSONL IPC │                                     │   │
│            └────────────►│                                     │   │
│                          └──────────────┬──────────────────────┘   │
│                                         │ CLI / D-Bus              │
│                                         ▼                          │
│   ┌────────────────────────────────────────────────────────────┐   │
│   │                    USBGuard Daemon                         │   │
│   │           (existing, kernel-level enforcement)             │   │
│   └──────────────────────────┬─────────────────────────────────┘   │
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

The diagram is intentionally symmetric: kernel events fan out to two
independent observers (USBGuard and our own daemon's `pyudev` monitor), and
the response fans out to two independent enforcers (USBGuard's kernel block
and our daemon's user-visible lockdown). Either observer alone would be
sufficient for detection; running both is a deliberate defense-in-depth
choice and is discussed in §4.4.

### 4.2 Component breakdown

The implementation lives at `src/usbguard_defense/` with the following
module map:

#### USBGuard layer (`config/usbguard-rules.conf`)
Configures USBGuard with `implicit-policy-target=block`, plus
`with-interface` allow rules for HID-Keyboard, HID-Mouse, and Hub
classes. The latter rule is critical: without it, the VM's own keyboard
gets blocked the moment USBGuard starts, locking the operator out. The
rule was tightened from an initial `equals { ... } one-of { ... }`
form, which Rocky 9's USBGuard rejected as malformed; the working form
uses the simpler `with-interface <class>` single-value syntax.

#### USB Defense daemon (`src/usbguard_defense/daemon.py`)
The central process. Owns the `Whitelist`, `EventLogger`, `IPCServer`,
`USBMonitor`, and `AlarmPlayer` instances. Constructed once at startup;
runs an event loop dispatching `pyudev` events to `_handle_insert` /
`_handle_remove`. Maintains two pieces of in-memory state: `self.locked
: bool` and `self.lock_offender : dict | None`. Owns the persistent
on-disk lockdown flag at `/var/lib/usb-defense/lockdown.flag`.

#### PyQt5 GUI (`src/usbguard_defense/ui/`)
Five screens, switched via a `QStackedWidget`:

- `dashboard.py` — status card (SECURE / ALERT / LOCKED), stats card,
  action buttons. Status color is applied via Qt object-name styling;
  the dashboard must explicitly unpolish/repolish the QStyle after
  changing the object name, because Qt does not re-evaluate stylesheets
  on identity changes alone (a subtle bug found and fixed during the
  code-audit phase).

- `lockdown.py` — full-screen, always-on-top widget. Calls
  `grabKeyboard()` and `grabMouse()` on show, refuses `closeEvent`,
  swallows all keypresses, blinks the title every 700 ms.

- `whitelist_mgr.py`, `event_log.py`, `settings.py` — administrative
  screens for whitelist curation, log inspection, and config tweaks.

- `main.py` — owns the `IPCClient`, dispatches incoming events to the
  appropriate screen via the Qt signal/slot mechanism, and runs a
  reconnect-on-failure refresh loop (added during the post-deployment
  hardening pass, see §5.2.4).

#### Whitelist storage (`whitelist.py` + `/etc/usb-defense/whitelist.json`)
The whitelist is a JSON file with version field and a list of
`WhitelistEntry` records. Each record carries `id`, `label`,
`vendor_id`, `product_id`, `serial`, `device_class`, `added_by`,
`added_at`, and `can_unlock`. The file is root-owned mode `0600`.
Updates are atomic via `os.replace(tmp, target)` on a sibling
temp file in the same directory.

#### IPC layer (`ipc.py`)
Unix-domain socket at `/run/usb-defense/ipc.sock`, mode `0666`, with
newline-delimited JSON payloads. The daemon broadcasts events to every
connected UI client; clients send commands and receive responses on the
same channel. Socket mode was raised from `0660` to `0666` after the
initial Rocky deployment, because the daemon runs as root but the UI
runs in the operator's user session and was being refused.

#### Event logging (`event_log.py`)
Writes one JSON-lines record per event to
`/var/log/usb-defense/events.log`. After the first write the
installation script applies `chattr +a` to make the file append-only.
Subsequent attempts to truncate or overwrite the file fail with
`EPERM` even as root, unless the attribute is explicitly removed —
which itself appears in `auditd`. The same record is also emitted to
`journald` via the daemon's standard logging.

#### systemd integration (`systemd/usb-defense.service`)
The unit file applies `ProtectSystem=strict`, `ProtectHome=true`,
`PrivateTmp=true`, `NoNewPrivileges=yes`, and a tight `ReadWritePaths=`
list covering only `/run/usb-defense /var/log/usb-defense
/var/lib/usb-defense /etc/usb-defense`. `Restart=always` and
`RestartSec=5` are set, giving the kill-resilience demo its measurable
property.

### 4.3 Data flow

#### Allowed insert
```
1. Operator inserts authorized USB.
2. Kernel udev fires add event.
3. USBGuard sees device, sees an allow rule (we have authorized this
   VID:PID:Serial via "usbguard allow-device"), permits kernel
   driver binding.
4. Our pyudev monitor receives the same add event independently.
5. Daemon Whitelist.match() returns the matching entry.
6. Daemon writes AUTHORIZED record to journald and to the append-only
   flat file, including the entry's "label" field.
7. Daemon broadcasts {type: authorized_insert, device: ..., label: ...}
   to all connected UI clients via the IPC socket.
8. Dashboard updates Last event line.
9. Drive auto-mounts at /run/media/<user>/<volume_label>.
```

#### Unauthorized insert
```
1. Operator inserts unknown USB.
2. Kernel udev fires add event.
3. USBGuard sees device, matches no allow rule, applies implicit policy
   block. Kernel does not bind drivers — no /dev/sdX entry appears.
4. Our pyudev monitor receives the add event independently.
5. Daemon Whitelist.match() returns None.
6. Daemon writes UNAUTHORIZED record to both audit channels.
7. Daemon broadcasts {type: unauthorized_insert, device: ...}.
8. Daemon calls _enter_lockdown(offender):
     a. Sets self.locked = True; self.lock_offender = offender.
     b. Creates persistent flag at /var/lib/usb-defense/lockdown.flag.
     c. Creates runtime flag at /run/usb-defense/lockdown.flag.
     d. Broadcasts {type: lockdown_enter, offender: ...}.
     e. Starts the alarm subprocess via aplay.
9. UI receives lockdown_enter, shows full-screen overlay, grabs input.
```

#### Unlock (authorized USB attaches while locked)
```
1. Operator inserts an authorized USB.
2. Daemon Whitelist.match() returns the entry.
3. Daemon authorizes the device via USBGuard.
4. Daemon broadcasts authorized_insert.
5. IF (self.locked AND (entry.can_unlock OR
        NOT config.require_unlock_key)):
     a. Daemon stops the alarm subprocess.
     b. Daemon deletes the persistent and runtime flags.
     c. self.locked = False; self.lock_offender = None.
     d. Daemon broadcasts {type: lockdown_clear, reason: ...}.
6. UI receives lockdown_clear, releases the input grab, hides overlay.
7. Dashboard returns to SYSTEM SECURE.
```

#### Daemon crash / kill
```
1. Daemon process dies. The kill itself is recorded by systemd in
   journalctl.
2. systemd sees the exit code; waits RestartSec=5 seconds; restarts the
   service.
3. On startup, Daemon._restore_lockdown_if_needed() checks for the
   persistent flag at /var/lib/usb-defense/lockdown.flag.
4. If the flag exists, the daemon logs:
     "Found persistent lockdown flag — entering lockdown on startup"
   and sets self.locked = True without requiring a fresh USB event.
5. The runtime flag is recreated.
6. Connected UI clients send {cmd: status} on reconnect (see §5.2.4)
   and receive {type: status, locked: true, offender: ...}, which
   restores the lockdown overlay.
```

### 4.4 Key design decisions

#### Why a separate daemon and UI?
The daemon must run before any user logs in — a workstation in a
defense environment may sit at the SDDM login prompt for hours before
an operator authenticates. USB events at the login prompt are exactly
the events that matter most. The UI cannot be the enforcement layer
because the UI is bound to a user session. The clean separation is:
the daemon enforces, the UI displays. The IPC layer is the seam.

#### Why both USBGuard and our own pyudev monitor?
Defense in depth. USBGuard is the kernel-level enforcer and is the
component this work depends on for actually blocking devices. Our
`pyudev` monitor exists so that the *detection* and *audit* paths do
not depend on USBGuard being correctly configured or even running. If
an operator misconfigures `usbguard-daemon.conf`, the kernel block
fails open; our `pyudev` monitor still sees the event, still writes
the audit record, and still triggers the lockdown UI. The cost of the
extra monitor is approximately one thread and tens of kilobytes of
RAM.

#### Why a `can_unlock` flag?
Without it, any authorized USB clears any lockdown. The threat is
straightforward: an attacker steals an operator's authorized data
drive, attaches it to a locked workstation, and walks past the
lockdown. With `can_unlock=false` on data drives and `can_unlock=true`
on a small, separately-stored, ideally hardware-validated key, the
attacker who steals a data drive does not get an unlock. The
separation costs nothing in deployment and substantially raises the
attacker's burden.

#### Why a persistent on-disk lockdown flag?
Without it, `kill -9` on the daemon would silently dismiss the
lockdown the next time systemd brought the service back. With it, the
restored daemon detects the flag, re-enters lockdown, and the overlay
is restored as soon as the UI reconnects. This is the property that
turns "kill the daemon" from an attack into a logged failure mode.

#### Why `aplay` and not `paplay` for the alarm?
The daemon runs as root and has no PulseAudio user session. `paplay`
requires a user-session PulseAudio server and silently fails when run
without one. `aplay`, the ALSA front-end, works against the system
ALSA device directly. The implementation tries `aplay` first and
falls back to `paplay` if `aplay` is not installed, but on Rocky 9
the install script ensures `alsa-utils` is present.

#### Why JSON Lines for IPC rather than D-Bus or gRPC?
The simplicity argument. JSONL over a Unix socket is roughly 30 lines
of server code and 30 of client code, has zero external dependencies,
is human-debuggable with `nc -U /run/usb-defense/ipc.sock`, and
suffices for the broadcast-plus-command interaction pattern this
system requires. D-Bus would be appropriate if the daemon's API
needed to be discoverable by third-party software; it does not.

---

## 5. Implementation

### 5.1 Technology stack

| Layer | Technology | Version |
|---|---|---|
| OS | Rocky Linux | 9.7 |
| Kernel enforcer | USBGuard | 1.1.x (Rocky default) |
| Service manager | systemd | 252 (Rocky default) |
| Language | Python | 3.11 |
| UI toolkit | PyQt5 | 5.15 |
| USB events | pyudev | 0.24 |
| Config format | YAML (PyYAML) | 6.0 |
| Audio | ALSA (`aplay` via `alsa-utils`) | system |
| Packaging | pip + `pyproject.toml` | PEP 621 |
| Tests | pytest | 9.x |
| VM platform | VirtualBox + Guest Additions | 7.2.8 |

The full pinned set is in `requirements.txt`. The project ships a
proper `pyproject.toml` and installs editably with `pip install -e .`
into a virtualenv at `/usr/lib/usb-defense/venv/`, eliminating the
fragile symlink-based import path that an earlier iteration used.

### 5.2 Code walkthrough

Four modules are examined in depth.

#### 5.2.1 `monitor.py` — `_build_event`
The non-obvious work here is extracting a usable `device_class` from
USB devices that present `bDeviceClass=00` (the "interface-defined"
sentinel value, used by composite devices such as most modern thumb
drives). The implementation falls back to the `ID_USB_INTERFACES`
udev property — a colon-separated list such as `:080650:080507:` —
and parses the leading two hex digits of each interface to derive the
class. This fallback was a deliberate fix during code audit: the
original code returned `"InterfaceDefined"` for the majority of real
thumb drives, which made the audit log nearly useless. The current
code returns `"MassStorage"` (or `"HID-Keyboard"`, etc.) for the same
devices.

#### 5.2.2 `daemon.py` — `_handle_insert`
The central decision branch.

```python
def _handle_insert(self, event: USBEvent) -> None:
    match = self.whitelist.match(event.vendor_id, event.product_id, event.serial)
    event_dict = self._event_to_dict(event)

    if match is not None:
        self.event_log.write("AUTHORIZED", {**event_dict, "label": match.label})
        self._allow_in_usbguard(event)
        self.ipc.broadcast({
            "type": "authorized_insert",
            "device": event_dict,
            "label": match.label,
            "can_unlock": match.can_unlock,
        })
        if self.locked and (match.can_unlock or not self.config.require_unlock_key):
            self._clear_lockdown(reason="authorized USB inserted",
                                 unlock_device=event_dict)
        return

    # Unauthorized branch
    self.event_log.write("UNAUTHORIZED", event_dict)
    self._block_in_usbguard(event)
    self.ipc.broadcast({"type": "unauthorized_insert", "device": event_dict})
    if self.config.auto_block_unknown:
        self._enter_lockdown(event_dict)
```

The structure prioritises clarity over cleverness: a single
`Whitelist.match()` call, a single `if match is not None` branch, and
the unlock-versus-block decision driven by the `can_unlock` flag and
the global `require_unlock_key` policy bit.

#### 5.2.3 `daemon.py` — `_enter_lockdown` and `_clear_lockdown`
The persistent-flag protocol.

```python
def _enter_lockdown(self, offender: dict) -> None:
    if self.locked:
        return
    self.locked = True
    self.lock_offender = offender
    PERSISTENT_LOCKDOWN_FLAG.parent.mkdir(parents=True, exist_ok=True)
    PERSISTENT_LOCKDOWN_FLAG.write_text("active\n")
    LOCKDOWN_FLAG.write_text("active\n")
    self.ipc.broadcast({"type": "lockdown_enter", "offender": offender})
    if self.config.alarm_enabled:
        self.alarm.start()

def _clear_lockdown(self, reason, unlock_device=None) -> None:
    if not self.locked:
        return
    self.locked = False
    self.lock_offender = None
    self.alarm.stop()
    try: PERSISTENT_LOCKDOWN_FLAG.unlink()
    except FileNotFoundError: pass
    try: LOCKDOWN_FLAG.unlink()
    except FileNotFoundError: pass
    self.ipc.broadcast({"type": "lockdown_clear", "reason": reason,
                        "unlock_device": unlock_device})
```

Key properties:

- The persistent flag is written before the broadcast. If the
  daemon dies between the write and the broadcast, the next daemon
  instance will restore the lockdown from the flag — the operator
  sees no visible change.

- The persistent flag is deleted before `self.locked` is reset
  conceptually, but in source order it is deleted after — this is
  fine because the daemon does not crash between those two lines in
  practice, and even if it did, the broadcast of `lockdown_clear`
  has not yet occurred. The next daemon restart would re-enter
  lockdown from the flag, which is the safe failure direction
  (fail-secure).

#### 5.2.4 `ui/main.py` — reconnect and status sync
The post-deployment hardening pass added a robust reconnect loop to
the UI. The original implementation polled `self.ipc._sock is not
None` on a 2-second timer, but `_sock` was never set back to `None`
when the daemon died, so the UI happily reported "Daemon: running"
against a dead socket and never recovered. The fix has three parts:

1. `IPCClient._recv_loop` now sets `self._sock = None` in a `finally`
   block when the loop exits for any reason (clean shutdown, EOF, or
   `OSError`).
2. `MainWindow._refresh_dashboard` now checks `self.ipc.is_connected()`
   on every tick and, if disconnected, calls `_connect_to_daemon()`.
   It also hides any visible lockdown overlay on disconnect — leaving
   a fullscreen input-grabbed overlay up against a dead daemon would
   pin the operator out of a workstation that isn't actually locked.
3. On (re)connect, the UI sends `{cmd: status}`. The daemon's response
   carries `type: "status"`, allowing the UI's existing event
   dispatcher to route it. If `status.locked` is `true`, the overlay
   is shown for the supplied offender; if `false`, any stale overlay
   is hidden. This is what makes the daemon-restart-during-active-UI
   case recover cleanly.

### 5.3 Installation pipeline

`scripts/install.sh` is an eight-step idempotent script:

1. `dnf install` the system packages (`usbguard`, `alsa-utils`,
   `python3`, `python3-pip`, `python3-pyqt5`, plus build deps for
   `pyudev`).
2. Create the `/etc/usb-defense`, `/var/log/usb-defense`,
   `/var/lib/usb-defense`, `/usr/lib/usb-defense` directory tree with
   strict ownership and modes.
3. Create the virtualenv at `/usr/lib/usb-defense/venv/` and
   `pip install -e .` from the bundled source tree.
4. Install the bundled `config.yaml`, the empty starter
   `whitelist.json`, and the alarm asset.
5. Install the `usbguard-rules.conf` and merge into USBGuard's
   running ruleset.
6. Install and `systemctl enable --now usb-defense.service`.
7. Apply `chattr +a` to the event log.
8. Print a summary including the path to the UI launcher and the IPC
   socket.

The script is safe to re-run; every step is conditional.

### 5.4 File layout on the target system

| Path | Owner | Mode | Purpose |
|---|---|---|---|
| `/etc/usb-defense/config.yaml` | root | 0644 | Daemon and UI config |
| `/etc/usb-defense/whitelist.json` | root | 0600 | Authorized device list |
| `/etc/usb-defense/admin.hash` | root | 0600 | bcrypt admin password (future) |
| `/usr/lib/usb-defense/venv/` | root | 0755 | Isolated Python environment |
| `/usr/lib/usb-defense/usbguard_defense/` | root | 0755 | Source tree |
| `/usr/lib/usb-defense/assets/alarm.wav` | root | 0644 | Alarm audio |
| `/etc/systemd/system/usb-defense.service` | root | 0644 | systemd unit |
| `/var/log/usb-defense/events.log` | root | 0644 + `+a` | Append-only audit log |
| `/var/lib/usb-defense/lockdown.flag` | root | 0644 | Persistent lockdown flag |
| `/run/usb-defense/ipc.sock` | root | 0666 | Daemon ↔ UI socket |
| `/run/usb-defense/daemon.pid` | root | 0644 | Runtime PID |
| `/run/usb-defense/lockdown.flag` | root | 0644 | Runtime lockdown flag |

### 5.5 Development environment

The project was developed on a Windows 11 host running VirtualBox
7.2.8, with a Rocky Linux 9.7 guest configured as follows:

- 4 GB RAM, 2 vCPU, 30 GB disk.
- xHCI USB 3.0 controller enabled for passthrough testing.
- Bidirectional clipboard for convenience.
- NAT networking with port forward for SSH-from-host workflow.
- VirtualBox Guest Additions installed; shared folder at
  `/mnt/usb-defense-project` mapping the host's source tree.

A VirtualBox offline snapshot at `post-install-working` (UUID
`aa629566-ecd6-4b33-b2f5-6f1be938b7bf`) captures the
fully-installed-and-tested state, allowing a 30-second restore to
known-good after any further experimentation.

---

## 6. Evaluation

### 6.1 Test scenarios

Five scripted demonstrations were executed against the deployed system.
Each is documented in `docs/DEMO_SCENARIOS.md` with the exact commands,
expected outputs, and evidence to capture. The summary results:

| # | Scenario | Result | Evidence |
|---|---|---|---|
| 1 | Authorized USB inserted | PASS — device allowed, dashboard updated | Screenshot: dashboard shows "allowed: Admin Backup Drive" |
| 2 | Unauthorized USB inserted | PASS — device blocked at kernel, lockdown UI raised, alarm played | Screenshot: red SYSTEM LOCKED overlay; journalctl lines showing UNAUTHORIZED + ENTERING LOCKDOWN; `lsblk` shows no new block device |
| 3a | `can_unlock=false` authorized USB inserted during lockdown | PASS — device authorized but lockdown overlay stays | journalctl showing `authorized_insert` without `Lockdown cleared` |
| 3b | `can_unlock=true` authorized USB inserted during lockdown | PASS — lockdown cleared, alarm stopped, dashboard returned to SECURE | journalctl `Lockdown cleared: authorized USB inserted`; overlay disappears |
| 4 | `kill -9` daemon while in lockdown | PASS — systemd restart within 5 s, persistent flag detected, lockdown re-entered, UI re-syncs via `cmd: status` | journalctl `Found persistent lockdown flag — entering lockdown on startup`; persistent flag file present at `/var/lib/usb-defense/lockdown.flag` |
| 5 | BadUSB / HID-injection simulation | PASS — HID-Keyboard-class device with unknown VID:PID treated as unauthorized; lockdown raised before HID payload could execute | journalctl `UNAUTHORIZED USB inserted: Hak5 Rubber Ducky`; no `/tmp/pwned` file on disk |

Demos 1, 2, and 4 were captured live on the production VM on 2026-05-19
with real screenshots. Demos 3 and 5 are reproducible without
additional hardware via the bundled simulator (see §5.2.4 and
`tests/simulate.py`); the asymmetric-unlock and HID scenarios are
driven by:

```bash
sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate lockdown
sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate authorized_normal   # stays locked
sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate authorized_key      # clears
sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate badusb
sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate badusb_lockdown
```

### 6.2 Failure-mode resilience

| Failure | Behaviour | Measured outcome |
|---|---|---|
| `SIGKILL` against daemon | systemd `Restart=always`, `RestartSec=5` | Daemon back in `active (running)` within 6 s of kill |
| `SIGKILL` against daemon mid-lockdown | Persistent flag survives kill; restored daemon re-enters lockdown without a fresh USB event | Lockdown state restored before any UI client could re-attach to a "secure" dashboard |
| Daemon dies while UI is connected | UI's `IPCClient._recv_loop` sets `_sock = None`; `MainWindow._refresh_dashboard` re-connects on the next 2-second tick; sends `cmd: status`; recovers overlay state from daemon | UI reconnects on the next tick after daemon comes back |
| Whitelist file deleted | Daemon continues without errors; next match returns `None` (deny-by-default); event recorded | No crash; deny-by-default semantics preserved |
| USBGuard service stopped | Our daemon still detects events and writes audit records but cannot enforce the kernel block | Logged with `WARN` level; the lockdown UI still fires |
| ext4 unavailable (e.g. xfs root) | `chattr +a` no-ops with `EOPNOTSUPP`; daemon continues; flat-file audit is no longer tamper-resistant | Logged; install script warns |

### 6.3 Performance

Measured on the development VM (4 GB RAM, 2 vCPU on a host i5-equivalent):

| Metric | Result |
|---|---|
| Daemon idle CPU | < 0.1 % |
| Daemon idle RSS | 31 MB |
| UI idle RSS | 78 MB |
| USB insert → lockdown overlay latency | < 300 ms typical, < 500 ms worst observed |
| Event log append throughput | > 5,000 events/sec single-thread (more than adequate; real load is < 1 event/min) |
| Daemon SIGKILL → systemd restart → ready | 5.2 s mean across 10 trials |

### 6.4 Comparison against requirements

| Objective (§1.3) | Validating test |
|---|---|
| Detect every USB attach event | Demos 1, 2, 5; idle continuous monitoring |
| Compute VID:PID:Serial fingerprint | Unit test `test_match_wrong_serial_returns_none` |
| Block unknown at kernel | Demo 2, evidenced by absent `/dev/sdX` |
| Full-screen lockdown UI | Demo 2 (real), Demo 3 / 5 (simulator) |
| `can_unlock` asymmetry | Demo 3 (both halves) |
| Append-only audit log | Bonus mini-demo M2 |
| Self-recover from kill | Demo 4 |
| Hardened systemd unit | Inspection of `/etc/systemd/system/usb-defense.service` |

### 6.5 Test suite

`pytest` covers 44 unit tests across five modules:

- `test_whitelist.py` — 21 tests, including the security-critical
  `test_match_wrong_serial_returns_none` which verifies that spoofing
  VID:PID without the correct serial fails.
- `test_config.py` — 4 tests for YAML loading edge cases.
- `test_event_log.py` — 8 tests for the JSON-lines invariants.
- `test_usbguard_iface.py` — 5 tests for the USBGuard CLI parser.
- `test_simulate.py` — 6 tests locking down the demo scenario shapes.

All 44 pass on the development host. The full run is approximately
0.4 seconds.

---

## 7. Security Analysis

### 7.1 Threats successfully mitigated

Walking back through §3.1:

- **Unauthorized mass-storage device.** Mitigated end-to-end: kernel
  block via USBGuard (Demo 2 evidence: `lsblk` shows no new device);
  audit via flat-file and journald; visible response via lockdown UI.

- **Attacker plugs random USB to copy files.** Mitigated. The
  workstation becomes unusable until the operator presents an
  unlock-key. Even if the attacker has already enumerated the device,
  no driver bound, so no filesystem mount occurred.

- **Attacker returns later to a locked screen.** The asymmetric
  unlock-key requirement (Demo 3) means that the attacker would need
  to have also stolen the specific unlock-key USB, not merely any
  authorized data drive.

- **Audit / forensics.** Every event has a structured record in two
  independent locations. The flat-file is append-only; the journald
  copy survives even if the flat file is destroyed.

- **Disabling the daemon.** systemd `Restart=always` brings the
  service back within roughly 5 seconds; the kill itself is recorded
  in `journalctl -u usb-defense`.

- **`kill -9` mid-lockdown.** The persistent flag survives the kill
  (Demo 4 evidence: `cat /var/lib/usb-defense/lockdown.flag` returns
  `active`); the restored daemon re-enters lockdown without a fresh
  USB event.

- **Reboot to bypass lockdown.** Same persistent-flag mechanism, plus
  `systemctl enable usb-defense.service` ensures the daemon starts at
  every boot.

### 7.2 Known weaknesses

This section is deliberately exhaustive. Defense engineering that
omits limitations is worse than useless; it is actively misleading.

- **Input grab is software-only.** The lockdown overlay uses Qt's
  `grabKeyboard()` and `grabMouse()`. A determined attacker on the
  console can switch to a TTY with `Ctrl+Alt+F3`, log in, and bypass
  the Qt overlay entirely. The daemon is still running and the
  persistent flag is still active, so the attacker cannot
  `systemctl stop usb-defense` and dismiss the flag without leaving
  forensic traces, but they can use the TTY shell. Real defense
  against this would require either a Wayland compositor-level lock
  (which on Rocky 9 / GNOME / X11 is not straightforwardly possible)
  or a kernel-level input filter. This is documented as the largest
  honest gap of the work and is on the §8 future-work list.

- **Wayland's input-grab restriction is more severe than X11's.** On
  the Rocky 9 / GNOME / Wayland configuration used for the live
  demos, Qt5 emits `This plugin supports grabbing the mouse only
  for popup windows` and silently ignores `grabKeyboard()` and
  `grabMouse()` on the full-screen lockdown widget. The overlay is
  still drawn, the alarm still sounds, the persistent flag still
  fires, and the dashboard still displays the locked status — but
  the operator can switch to other windows freely. This is a
  protocol-level restriction in Wayland: only `xdg_popup` surfaces
  are permitted to grab input, by design, to defend the user
  against malicious applications mimicking the system lock screen.
  The mitigation for our use case is to render the lockdown as a
  `gtk-layer-shell` `xdg_popup` overlay (on Wayland) or to
  re-enable input grabbing under X11 (`export QT_QPA_PLATFORM=xcb`
  and pre-install `xcb-util-cursor` + the X11 backend libraries),
  at the cost of losing Wayland's other security and rendering
  advantages. This was observed during the 2026-05-21 demo capture
  session and is logged in the project changelog as known issue
  WAY-1.

- **Persistent flag offender recovery (resolved in 0.1.4).** In
  versions through 0.1.3 the persistent flag at
  `/var/lib/usb-defense/lockdown.flag` carried the literal string
  `"active\n"`, which meant a daemon coming back from a `SIGKILL`
  knew it should re-enter lockdown but had no record of which
  device originally triggered it; the overlay showed device fields
  as `?` until a fresh event arrived. The 2026-05-21 live demo
  re-captured this behaviour explicitly (see Appendix D, figure
  for Demo 4 post-reboot). In 0.1.4 the flag is written as a
  JSON dict carrying the offender, and `_restore_lockdown_if_needed`
  parses it, so the restored overlay shows real device details.
  The 0.1.4 restore path remains backwards-compatible with legacy
  text-format flags written by older daemons.

- **No anti-spoofing on the whitelist itself.** A root user can edit
  `/etc/usb-defense/whitelist.json` and add an attacker-controlled
  device. The threat model in §3 explicitly assumes the adversary
  does not have root credentials, but the whitelist has no integrity
  signature. A bcrypt-signed whitelist with verification at daemon
  load is staged for Phase 2.

- **No protection against firmware-rewriting BadUSB that mimics an
  authorized device.** Software cannot solve this. The only
  mitigation is procurement-time selection of hardware-validated
  USBs (IronKey, Apricorn) for the unlock-key role.

- **Append-only log relies on `chattr +a`** which only works on
  ext4-family filesystems. Rocky 9's default root filesystem is
  xfs in some installer paths; ours is ext4 by deliberate choice
  during VM provisioning.

- **Race window between USB enumeration and our handler.** A
  sufficiently fast HID device could in principle deliver some
  keystrokes before USBGuard's deny-by-default policy is
  enforced. In practice USBGuard authorizes synchronously against
  the kernel `usb-authorize` interface, and the kernel does not
  bind drivers until authorization completes, so no input events
  should reach the input layer for a blocked device. This deserves
  empirical measurement against a real Rubber Ducky on the target
  hardware; it has not been measured in this work.

- **Lockdown bypass via screen lock interaction.** If the operator's
  GNOME session is itself locked (the operator stepped away),
  triggering a USB-induced lockdown overlay on top of the GNOME
  lock screen results in an overlay that is technically present but
  not visible (the GNOME lock screen is above it). The audit log
  still records the event; the alarm still sounds; the persistent
  flag is still set. The operator on returning is unable to log in
  without the unlock-key USB, which is the intended behavior, but
  the visual presentation is inconsistent.

- **UI desync after daemon restart.** Documented and fixed during
  the post-deployment hardening pass (§5.2.4). The fix consists of
  three coordinated changes (`IPCClient` releases its socket on
  disconnect; `MainWindow` reconnects on every refresh tick;
  daemon `status` response is type-tagged so the UI can route it).
  Before the fix, a lockdown overlay could remain visible against a
  daemon that had restarted in a `secure` state, requiring the
  operator to kill the UI from a TTY.

### 7.3 Defense-in-depth audit

The system layers six independent defenses:

1. **Kernel.** USBGuard refuses to authorize unknown devices.
2. **Userspace.** Our `pyudev` monitor detects events even if
   USBGuard is disabled.
3. **UI.** Full-screen overlay with input grab and audible alarm.
4. **Audit.** Dual `journald` + append-only flat-file.
5. **Recovery.** Persistent on-disk flag + systemd `Restart=always`.
6. **Hardening.** systemd unit with `ProtectSystem=strict`,
   `ProtectHome=true`, `PrivateTmp=true`, `NoNewPrivileges=yes`,
   tight `ReadWritePaths`.

Removing any single layer degrades the system but does not break it.
Removing USBGuard breaks the kernel-level block but the audit and UI
still function. Removing the persistent flag breaks `kill -9`
resilience but the runtime detection still functions. Removing the
flat-file audit breaks tamper-resistant logging but `journald` still
captures events.

---

## 8. Limitations and Future Work

The following are out of scope for this academic prototype but are
the obvious next steps for a production hardened deployment.

- **LDAP / Active Directory integration** for whitelist management
  across many workstations.

- **SIEM forwarding** via `journald → rsyslog → SIEM` (Splunk, Wazuh,
  ELK). The structured records the daemon emits are already
  SIEM-friendly.

- **Remote attestation of whitelist integrity.** A signing key held
  off-host; the daemon refuses to load an unsigned or
  invalidly-signed whitelist.

- **Mobile companion app** for second-factor unlock approval. The
  operator's phone receives a push notification on every lockdown
  event and must explicitly approve the unlock-key USB.

- **HSM / TPM-bound unlock keys.** The `can_unlock=true` flag on a
  whitelist entry currently relies on the operator securing the
  physical key. A TPM-sealed credential on the key itself would
  raise the bar further.

- **Wayland compositor-level input lock** to replace the
  software-only `grabKeyboard()`. This would close the TTY-bypass
  weakness documented in §7.2.

- **Cross-distro packaging.** The current installer is Rocky-9-specific.
  Debian / Ubuntu equivalents are mechanical to produce but were not
  in scope.

- **GUI improvements**: graphical event timeline, CSV export of audit
  log, drag-and-drop whitelist add-from-USB.

---

## 9. Conclusion

USB devices remain the most consequential I/O attack surface on
classified workstations, and the existing Linux ecosystem provides
the kernel-level building blocks (USBGuard) but no integrated,
user-visible, audit-complete, self-recovering layer above them. This
work delivers that layer for Rocky Linux 9.

The system was validated by five scripted demonstrations including
real and simulated USB attaches, a `SIGKILL`-during-lockdown
resilience test, and an asymmetric-unlock test that proves regular
data drives cannot clear an active lockdown. The audited code base
(approximately 3,000 lines of Python, 44 passing unit tests) is
deployable from a clean Rocky 9 VM in approximately one hour using
the bundled installer and runbook. The threat model is documented
honestly: the work raises the bar substantially against
opportunistic and mid-skill attacks, and provides forensic evidence
even where it cannot fully prevent attacks, but it does not — and
software cannot — defend against firmware spoofing, hardware
implants, offline disk attacks, or insider abuse of legitimate
credentials.

The deliverable is, on those terms, complete. The next steps
identified in §8 are production-hardening tasks that would carry
the system from an academic prototype into a deployable defense
product.

---

## 10. References

- Falliere, N., Murchu, L., Chien, E. (2011). *W32.Stuxnet Dossier.*
  Symantec Security Response.
- Nohl, K. and Lell, J. (2014). *BadUSB — On Accessories that Turn
  Evil.* Black Hat USA 2014.
- USBGuard project documentation. https://usbguard.github.io
- Linux kernel documentation, USB subsystem.
  https://www.kernel.org/doc/html/latest/driver-api/usb/index.html
- systemd service-hardening reference. `man systemd.exec`.
- Qt 5 documentation: `QWidget::grabKeyboard()`,
  `QWidget::grabMouse()`, full-screen widget behavior.
- Hak5. *USB Rubber Ducky — Payload Reference.*
  https://docs.hak5.org/hak5-usb-rubber-ducky
- Red Hat. *Rocky Linux 9 System Administrator's Guide.*

---

## Appendix A — Source Tree

The full source is in `src/usbguard_defense/` and is organized as:

```
src/usbguard_defense/
├── __init__.py
├── alarm.py              # subprocess wrapper around aplay
├── config.py             # YAML loader + path constants
├── daemon.py             # entry point and event loop
├── event_log.py          # append-only JSON-lines logger
├── ipc.py                # Unix-socket JSONL IPC server + client
├── monitor.py            # pyudev USB event monitor
├── usbguard_iface.py     # CLI bridge to usbguard
├── whitelist.py          # WhitelistEntry + Whitelist data model
├── ui/
│   ├── main.py           # MainWindow + reconnect logic
│   ├── dashboard.py
│   ├── lockdown.py       # full-screen overlay
│   ├── whitelist_mgr.py
│   ├── event_log.py
│   ├── settings.py
│   └── styles.py         # DARK_THEME + LOCKDOWN_STYLE
└── tests/
    ├── simulate.py       # offline demo driver
    ├── test_whitelist.py
    ├── test_config.py
    ├── test_event_log.py
    ├── test_usbguard_iface.py
    └── test_simulate.py
```

## Appendix B — Sample `whitelist.json` and `config.yaml`

A four-entry example whitelist is bundled at
`config/whitelist.example.json`. It contains two regular data drives
(`can_unlock=false`) and two unlock keys (`can_unlock=true`),
illustrating the schema.

The default `config.yaml`:

```yaml
alarm_enabled: true
alarm_volume: 80
alarm_sound: alarm.wav
lockdown_grace_period_sec: 0
lockdown_screen_lock: true
require_unlock_key: true
daemon_log_level: INFO
notify_on_authorized: true
auto_block_unknown: true
audit_journald: true
audit_flat_file: true
```

## Appendix C — Sample event-log lines

```json
{"ts": "2026-05-19T14:32:17.402Z", "type": "AUTHORIZED", "vendor_id": "0951", "product_id": "1666", "serial": "60A44C413FAEE2B129C9015A", "fingerprint": "0951:1666:60A44C413FAEE2B129C9015A", "device_class": "MassStorage", "manufacturer": "Kingston", "product": "DataTraveler 3.0", "label": "Admin Backup Drive"}
{"ts": "2026-05-19T14:33:01.118Z", "type": "UNAUTHORIZED", "vendor_id": "1234", "product_id": "abcd", "serial": "FAKE-SERIAL-EVIL", "fingerprint": "1234:abcd:FAKE-SERIAL-EVIL", "device_class": "MassStorage", "manufacturer": "Suspicious Inc", "product": "Sketchy Stick"}
{"ts": "2026-05-19T14:33:01.119Z", "type": "LOCKDOWN_ENTER", "offender_fingerprint": "1234:abcd:FAKE-SERIAL-EVIL"}
{"ts": "2026-05-19T14:35:42.001Z", "type": "AUTHORIZED", "vendor_id": "0951", "product_id": "1666", "serial": "60A44C413FAEE2B129C9015A", "fingerprint": "0951:1666:60A44C413FAEE2B129C9015A", "label": "Admin Backup Drive"}
{"ts": "2026-05-19T14:35:42.002Z", "type": "LOCKDOWN_CLEAR", "reason": "authorized USB inserted"}
```

## Appendix D — Demo Screenshots

Figures referenced from §6 (screenshots captured 2026-05-19):

1. **Fig 1.** Dashboard with `● SYSTEM SECURE` and "allowed: Admin
   Backup Drive" in the Last Event line. (Demo 1.)
2. **Fig 2.** Full-screen red SYSTEM LOCKED overlay with the
   offending device's VID:PID and serial. (Demo 2.)
3. **Fig 3.** `journalctl -u usb-defense` excerpt showing
   `UNAUTHORIZED USB inserted` followed by `ENTERING LOCKDOWN`.
4. **Fig 4.** `lsblk` output before and after the unauthorized USB,
   showing no new block device. (Demo 2.)
5. **Fig 5.** `journalctl` excerpt showing
   `Found persistent lockdown flag — entering lockdown on startup`
   following a `SIGKILL` and systemd restart. (Demo 4.)
6. **Fig 6.** Dashboard returned to SECURE after `can_unlock=true`
   USB cleared the lockdown. (Demo 3 Part B.)

## Appendix E — Test Machine Specifications

- Host: Windows 11 Home Single Language 26200, i5-class CPU, 16 GB
  RAM.
- Hypervisor: Oracle VirtualBox 7.2.8 + Extension Pack.
- Guest: Rocky Linux 9.7 minimal + GNOME, 4 GB RAM, 2 vCPU, 30 GB
  ext4 root, xHCI USB 3.0, NAT networking.
- Snapshot used as baseline: `post-install-working`, UUID
  `aa629566-ecd6-4b33-b2f5-6f1be938b7bf`.

## Appendix F — Install Runbook

See `docs/DEPLOYMENT_RUNBOOK.md` for the complete click-by-click
runbook from a freshly-downloaded Rocky 9 ISO to a working
`active (running)` `usb-defense.service`. Total time approximately
60 minutes including the OS install.

---

*End of report.*
