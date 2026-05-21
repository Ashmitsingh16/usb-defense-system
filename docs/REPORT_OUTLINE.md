# Final Report — Outline

Skeleton for the academic write-up. Each section lists what to put in it, roughly how long, and which artifact in this repo supplies the raw material.

**Target length:** 20–30 pages including figures.
**Audience:** evaluators + senior project guide.
**Tone:** academic but honest — explicitly state limits, do not over-claim.

---

## Title page

> **USB Defense System for Defense-Grade Hardened Workstations**
> *A whitelist-enforced, lockdown-capable USB security layer for Rocky Linux 9*
> 
> Author: Ratnesh Sharma
> Roll No: ______
> Guide: ______
> Department / Institute: ______
> Submission date: ______

---

## Abstract  (~250 words)

State the problem (USB as an attack vector in classified environments), the gap (no end-to-end open-source workstation-level solution combining kernel block + user-visible lockdown + audit trail), the contribution (this system), the validation method (five scripted demos including a BadUSB scenario), and the honest scope (Linux workstation only, software-detectable threats only).

**Source material:** `docs/ARCHITECTURE.md` §1 and §2.

---

## 1. Introduction  (~2 pages)

### 1.1 Motivation
Stuxnet, BadUSB family, real-world data-exfiltration via thumb drives. Cite a few headline incidents. State why defense-sector workstations are particularly exposed.

### 1.2 Problem Statement
One paragraph. Use the exact wording from `ARCHITECTURE.md` §1.

### 1.3 Objectives
- Detect every USB connection event on a Rocky Linux 9 workstation.
- Cross-check device fingerprint (VID:PID:Serial) against an admin-curated whitelist.
- Block unknown devices at the kernel level.
- Trigger a full-screen, input-grabbing lockdown UI with audible alarm.
- Distinguish "trusted data drives" from "unlock-key" USBs.
- Produce a tamper-resistant audit log.
- Self-recover from daemon crashes / process kills.

### 1.4 Scope and Non-Scope
Reproduce the two tables from `ARCHITECTURE.md` §2 verbatim. This is the single most important section for your evaluator — it proves you understand the limits of your work.

---

## 2. Background and Related Work  (~3 pages)

### 2.1 USB attack surface
Brief survey of USB threats:
- Mass-storage exfiltration / malware introduction.
- BadUSB firmware-spoofing (Karsten Nohl, 2014).
- HID-injection devices (Rubber Ducky, Bash Bunny).
- Network adapter injection (LAN Turtle).
- Power-line / juice-jacking (mention but acknowledge out of scope).

### 2.2 Existing defenses surveyed
- **USBGuard** (existing Linux tool — we use it as kernel-level enforcer).
- **udisks2 / udev rules** — lighter-weight but no lockdown UI.
- Commercial: DeviceLock, McAfee Device Control, Microsoft Defender Device Guard.
- Hardware: IronKey, Apricorn — secure at procurement, no software needed.

### 2.3 Gap our project fills
Open-source, full-stack (kernel block + GUI lockdown + audit log + self-recovery), targeted at a Rocky Linux defense-grade workstation, with explicit "unlock key" separation. Most existing tools stop at "block it"; we add "and force the operator to physically present an authorized device before they can use the machine again".

---

## 3. Threat Model  (~2 pages)

Reproduce `ARCHITECTURE.md` §2 with elaboration on each row.

**Add an assumption block:**
- Adversary has physical access to USB ports but not to the disk (mitigated by LUKS, separate work).
- Adversary does not have root credentials.
- Workstation is in a controlled environment (not a hostile network at the OS layer).
- Software cannot detect firmware spoofing — accepted limitation.

---

## 4. System Design  (~4 pages)

### 4.1 Architecture overview
Insert the ASCII diagram from `ARCHITECTURE.md` §3. Walk through each component.

### 4.2 Component breakdown
For each, one paragraph + 1–2 code references:
- **USBGuard layer** — kernel-level enforcement; we configure it with a deny-by-default policy in `config/usbguard-rules.conf`.
- **USB Defense Daemon** (`src/usbguard_defense/daemon.py`) — long-running Python process; structure: monitor thread → callback → whitelist match → branch (allow vs lockdown).
- **PyQt5 GUI** (`src/usbguard_defense/ui/`) — five screens; lockdown overlay uses `grabKeyboard()`/`grabMouse()` for input capture.
- **Whitelist storage** (`whitelist.py` + `whitelist.json`) — root-owned, mode 0600, atomic replace on update.
- **IPC layer** (`ipc.py`) — Unix-domain socket + line-delimited JSON, multiplexed broadcast to multiple UI clients.
- **Event logging** (`event_log.py`) — append-only flat file (`chattr +a`) plus journald.
- **systemd integration** (`systemd/usb-defense.service`) — `Restart=always`, `ProtectSystem=strict` hardening.

### 4.3 Data flow diagrams
Reproduce the four flow blocks from `ARCHITECTURE.md` §5 (allowed insert, unauthorized insert, unlock, daemon crash/tamper).

### 4.4 Key design decisions and rationales
- **Why a separate daemon and UI?** Daemon needs to run before any user logs in; UI lives in the user session. The IPC layer is the seam.
- **Why both USBGuard AND our own monitor?** Defense in depth. USBGuard could be misconfigured or have a bug; we cross-check via `pyudev` independently.
- **Why `can_unlock` flag?** Otherwise a stolen authorized USB could clear a lockdown. Splitting "data drives" from "keys" raises the bar for the attacker.
- **Why persistent lockdown flag on disk?** So that `kill -9` on the daemon does not silently dismiss the lockdown on restart.
- **Why `aplay` not `paplay`?** Daemon runs as root with no user audio session; ALSA `aplay` works without one.

---

## 5. Implementation  (~5 pages)

### 5.1 Tech stack and dependencies
Table: Rocky 9 / Python 3.11 / PyQt5 / pyudev / PyYAML / USBGuard / systemd / ALSA. Reference `requirements.txt`.

### 5.2 Code walkthrough
Pick the four most interesting modules and explain them with code excerpts (~10–20 lines each):
1. **`monitor.py` `_build_event`** — extracting VID/PID/Serial + interface-class fallback for composite devices.
2. **`daemon.py` `_handle_insert`** — the central decision branch.
3. **`daemon.py` `_enter_lockdown` + `_clear_lockdown`** — persistent flag handling.
4. **`ui/lockdown.py`** — full-screen overlay + input grab + `closeEvent` refusal.

### 5.3 Installation pipeline
Summarize `scripts/install.sh`. Note the security-hardened systemd unit options (`ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`, `NoNewPrivileges=yes`, restricted `ReadWritePaths`).

### 5.4 Configuration and deployment paths
Reproduce the file-layout table from `ARCHITECTURE.md` §6.

### 5.5 Development environment
VirtualBox 7.2 + Rocky Linux 9 + 4 GB / 2 vCPU / 30 GB. Shared-folder workflow for code transfer. Snapshot strategy (post-install-clean).

---

## 6. Evaluation  (~4 pages)

### 6.1 Test scenarios
List the five demos from `docs/DEMO_SCENARIOS.md` with:
- Setup
- Procedure
- Expected vs observed behavior
- Screenshot reference (figures 1..N)

### 6.2 Failure-mode resilience tests
- Daemon SIGKILL — measure restart time (target < 6 s; systemd `RestartSec=5`).
- Daemon SIGKILL during lockdown — verify lockdown is restored.
- Whitelist file deleted while daemon running — verify daemon handles gracefully on next reload.
- USBGuard service stopped — verify our daemon still detects and logs (just can't enforce kernel block).

### 6.3 Performance characteristics
- Daemon idle CPU: ~0.1% (event-driven).
- Daemon idle RSS: ~25–35 MB.
- USB insert → lockdown overlay latency: <300 ms typical.
- Event log throughput: handles ~hundreds of events/second easily (single-file append).

Run `ps`, `top`, `time` to back these numbers with real measurements.

### 6.4 Comparison against requirements
Table mapping each Objective (§1.3) to the test that validates it.

---

## 7. Security Analysis  (~2 pages)

### 7.1 Threats successfully mitigated
Walk back through the threat model table; for each row that says "DEFEND AGAINST", cite which demo proves it.

### 7.2 Known weaknesses (be honest)
- **Input grab is software-only.** A determined attacker on the console can switch to a TTY (`Ctrl+Alt+F3`) and bypass the Qt overlay. Real defense would need a Wayland compositor lock or a kernel-level input filter.
- **No anti-spoofing on the whitelist itself.** Root can edit it. Bcrypt-signed whitelist + remote attestation is Phase 2.
- **No protection against firmware-rewriting BadUSB** that mimics an authorized device's VID:PID:Serial. Hardware-validated USBs are the only mitigation.
- **Append-only log relies on `chattr +a`** — only works on ext4-family filesystems.
- **Race window:** between USB enumeration and our handler running, a sufficiently fast HID payload could in theory deliver some keystrokes before USBGuard finishes blocking. In practice USBGuard authorizes synchronously before the kernel binds drivers, so this should not be exploitable; worth measuring.

### 7.3 Defense-in-depth audit
- Kernel: USBGuard.
- Userspace: our daemon.
- UI: lockdown overlay + alarm.
- Audit: dual journald + append-only flat file.
- Recovery: persistent flag + systemd restart.
- Hardening: dedicated `User=root`, `ProtectSystem=strict`, `NoNewPrivileges`.

---

## 8. Limitations and Future Work  (~1 page)

Use `ARCHITECTURE.md` §11 as the seed and expand:
- LDAP / AD integration for multi-user.
- SIEM forwarding (e.g. journald → rsyslog → SIEM).
- Remote attestation of whitelist integrity.
- Mobile companion app for unlock approval.
- HSM/TPM-bound unlock keys.
- Wayland compositor-level input lock (replace `grabKeyboard`).
- Cross-distro packaging (Debian/Ubuntu, not just Rocky).

---

## 9. Conclusion  (~1 page)

Restate problem, summarise contribution, restate evaluation result, restate scope honestly. Two paragraphs.

---

## 10. References

- Nohl, K. & Lell, J. (2014). *BadUSB — On Accessories that Turn Evil.* Black Hat USA.
- USBGuard project — https://usbguard.github.io
- Falliere, N., Murchu, L., Chien, E. (2011). *W32.Stuxnet Dossier.* Symantec.
- Linux kernel USB subsystem documentation.
- systemd service-hardening reference.
- Qt 5 — input grabbing and full-screen widget docs.
- Add whatever specific URLs / papers you cite in §2.

---

## Appendices

- **A.** Full source-code listing (or link to the repo).
- **B.** Sample `whitelist.json` and `config.yaml`.
- **C.** Sample event-log entries (real, from a demo run).
- **D.** Screenshots from all five demos (figures 1–N referenced in §6).
- **E.** Test machine spec sheet (host: Windows 11 + i5/Ryzen / 16 GB RAM; guest: Rocky 9 / 4 GB / 2 vCPU; VirtualBox 7.2.8).
- **F.** Install runbook (use `docs/DEPLOYMENT_RUNBOOK.md` verbatim).

---

## Writing checklist before submission

- [ ] Every figure has a caption AND is referenced from the body.
- [ ] Threat-model table appears at least once, ideally twice.
- [ ] Honest "limitations" section — don't trim it.
- [ ] Each demo has a screenshot or log excerpt as evidence.
- [ ] Code excerpts are syntax-highlighted (use `\begin{minted}{python}` if LaTeX).
- [ ] Bibliography is alphabetised and consistent.
- [ ] Acknowledgements page (guide, senior, anyone who helped).
- [ ] Plagiarism check passes.
- [ ] One full read-through aloud — catches awkward phrasing the eye misses.
