# Viva Cheat Sheet — print this and bring it

## 60-second pitch
*"Four-layer defense — kernel block via USBGuard, userspace policy daemon in Python, full-screen GUI lockdown with audible alarm, tamper-resistant audit log — that hardens a Rocky Linux 9 workstation against unauthorized USB devices. v0.2.0 adds password-gated whitelist edits, HMAC-signed whitelist file with fail-closed verification, TTY-escape blocking, and a one-time paper recovery code. Uses an asymmetric trust model where regular authorized USBs can mount but only USBs explicitly marked as 'unlock keys' can clear a lockdown."*

## Numbers to drop into answers

| Metric | Value |
|---|---|
| Version | **0.2.0** (Phase 1 hardening) |
| Python files | **22** (13 daemon-side + 7 UI + 2 helper) |
| Unit tests passing | **82 / 82** (4 POSIX-only skipped) |
| Defense layers | **6** (kernel, daemon, UI, audit, password gate, HMAC integrity) |
| Daemon restart latency | **~1 s** (systemd `RestartSec=1`, watchdog 30 s) |
| USB → lockdown latency | **~300 ms** typical |
| Daemon idle RSS | **~30 MB** |
| Open network ports | **0** (Unix socket only) |
| Password hash | **argon2id** (t=3, m=64 MiB, p=2) |
| Whitelist signature | **HMAC-SHA256** with 32-byte key, 0600 root:root |
| Paper recovery code entropy | **80 bits** (16 Crockford-Base32 chars) |

## Top 10 anticipated questions — with prepared answers

**Q1. Why both USBGuard AND your own daemon?**
USBGuard is the *kernel enforcer*. Our daemon is the *policy + UX layer*: lockdown UI, alarm, the asymmetric `can_unlock` trust model, the persistent-flag paranoid restart, and the independent pyudev cross-check (defense in depth — a USBGuard bug doesn't blind us).

**Q2. What if I kill your daemon?**
systemd restarts within 5 s (`Restart=always`). On restart, the daemon reads `/var/lib/usb-defense/lockdown.flag` — if present, it re-enters lockdown immediately. Attacker would need to kill the daemon AND delete the flag AND stop systemd — all logged, all require root.

**Q3. BadUSB can spoof VID/PID/Serial. Doesn't that defeat you?**
Yes — and we *say so* in the threat model. Software cannot detect firmware spoofing. Mitigation is at procurement: hardware-validated USBs like IronKey. Our system raises attack cost (attacker needs exact authorized fingerprint AND a BadUSB controller) but cannot make it zero.

**Q4. What stops root from editing the whitelist?**
v0.2.0 added HMAC-SHA256 signing of `whitelist.json` against `whitelist.sig`. Key (`master.key`, 0600 root) is generated once at install. On every daemon start (and after `systemctl restart usb-defense`), the whitelist is verified — any mismatch logs `WHITELIST_TAMPER` and the daemon **fails closed**, treating the whitelist as empty so every USB triggers lockdown. A root attacker who *also* reads the key can re-sign, but that's a much higher bar than "vim the JSON" — and the tamper event still hits the append-only audit log first. Off-machine log shipping to defeat the rogue-root case is parked for Phase 4 (needs network — out of Phase 1 scope by user requirement).

**Q5. Why Python? Isn't it slow?**
The system bottleneck is human reaction (~250 ms) and audio latency, not Python overhead. Event-driven design means ~0% CPU idle, ~30 MB RAM. Python's iteration speed pays off — policy changes take minutes not hours.

**Q6. Why not D-Bus for IPC?**
Extra dependency, more complex, no advantage at this scale. Unix-domain socket + JSON lines is local-only (zero network attack surface), debuggable with `nc -U`, multiplexed for multiple UI clients.

**Q7. What about two USBs plugged at the same time, one authorized one not?**
**Strictest wins.** Unauthorized triggers lockdown regardless of the authorized USB also being present. Documented in `ARCHITECTURE.md` §9.

**Q8. The lockdown overlay uses Qt's `grabKeyboard`. Can't I just `Ctrl+Alt+F3` to a TTY?**
**Partially mitigated in v0.2.0, but a residual gap exists (tracked as TTY-1).** v0.2 ships two defenses: (a) `/etc/X11/xorg.conf.d/99-usbdefense-novtswitch.conf` with `Option "DontVTSwitch" "True"` — works against raw X clients but NOT against GNOME's Mutter, which routes VT-switch combos via logind; (b) `systemctl mask getty@tty2..6` from the daemon — covers explicit starts but NOT logind's dynamic template instantiation. The honest answer is that **`Ctrl+Alt+F3` still works to reach a TTY login on the v0.2 acceptance build**, observed during VM testing on 2026-05-26. The proper fix is `NAutoVTs=0` + `ReserveVT=0` in `/etc/systemd/logind.conf` plus `systemctl restart systemd-logind`, scheduled for Phase 2 because it risked disrupting active sessions mid-acceptance. If asked directly: *"v0.2 narrows the gap but does not yet eliminate it — TTY-1 is the top Phase-2 ticket."*

**Q9. Why both journald AND a flat file for logging?**
Defense in depth for the audit trail itself. journald is queryable (`journalctl -u usb-defense -f`). The flat file uses `chattr +a` (append-only ext4 attribute) — even root cannot edit or delete without first removing the attribute, which itself is auditable. Two independent channels = attacker has to compromise both.

**Q10. What happens if the whitelist file is corrupted or malformed?**
Atomic-replace writes (`os.replace` after `.tmp`) prevent half-written files. If JSON is malformed, the daemon logs the error and treats whitelist as empty — **fail-secure** (everything unauthorized) not fail-open. v0.2.0 adds a stronger version: even a syntactically-valid JSON that's been hand-edited (no sig recomputed) fails HMAC verification and triggers the same fail-closed path.

**Q11 (new in v0.2). How does the admin password work? What if it leaks?**
Stored as **argon2id** hash at `/etc/usb-defense/admin.hash`, 0600 root:root. argon2id is memory-hard (64 MiB per verify) so offline brute force is expensive on consumer hardware. The daemon refuses to verify if the file permissions are weaker than 0600 — fails closed. Password leak means an attacker can edit the whitelist and clear lockdowns, but cannot extract the master key (separate file) to silently forge whitelist signatures, so the tamper event still fires. Recovery is via the paper code or re-running setup.

**Q12 (new in v0.2). What if the admin loses every unlock-USB AND forgets the password?**
The paper recovery code — 16 Crockford-Base32 chars, generated at install, displayed exactly once, written down by the admin and locked in a safe. Hashed at rest (argon2id), **one-time use** — after a successful verify the hash file is deleted and the admin is told to regenerate. 80 bits of entropy plus a slow KDF makes brute force infeasible. This is the "you have no other way in" escape hatch.

## File pointer reference — what to open if asked

| If asked about… | Open this |
|---|---|
| Architecture overview | `docs/ARCHITECTURE.md` |
| "Show me the main daemon logic" | `src/usbguard_defense/daemon.py` (start at `_handle_insert`) |
| "How do you watch USB events?" | `src/usbguard_defense/monitor.py` (`_build_event`) |
| "Show me the lockdown UI" | `src/usbguard_defense/ui/lockdown.py` |
| "How is the alarm played?" | `src/usbguard_defense/alarm.py` (note `aplay` not `paplay`) |
| "Show me your tests" | `src/usbguard_defense/tests/` — 82 tests |
| "How does the install work?" | `src/scripts/install.sh` (9 steps, ends with setup wizard) |
| "Show me the systemd hardening" | `src/systemd/usb-defense.service` |
| "How is the admin password stored?" | `src/usbguard_defense/auth.py` (argon2id) |
| "How is the whitelist tamper-checked?" | `src/usbguard_defense/integrity.py` + `whitelist.py::_load` |
| "Show the paper recovery code design" | `src/usbguard_defense/recovery.py` |
| "How does the setup ceremony work?" | `src/scripts/setup.py` |
| Schema of the whitelist | `src/config/whitelist.example.json` or `ARCHITECTURE.md` §7 |
| Threat model | `docs/PHASE1_DESIGN.md` §2 (current) or `ARCHITECTURE.md` §2 (v0.1 baseline) |
| Demo scripts | `docs/DEMO_SCENARIOS.md` |
| Phase 1 design + scope | `docs/PHASE1_DESIGN.md` |

## Last-minute pre-viva checklist

- [ ] Daemon is running: `sudo systemctl status usb-defense` → `active`
- [ ] UI launched and dashboard visible
- [ ] Authorized USB + unauthorized USB physically on hand
- [ ] One USB enrolled with `can_unlock=true`, one with `can_unlock=false`
- [ ] Live log open: `sudo journalctl -u usb-defense -f`
- [ ] `lsblk` ready in a separate terminal (to prove kernel never bound the unauthorized device)
- [ ] Snapshot `post-install-clean` exists in VirtualBox (instant rewind if anything breaks mid-demo)
- [ ] Slides open at slide 1
- [ ] Cheat sheet in your pocket

## Words to AVOID using

- ~~"perfect"~~, ~~"completely secure"~~ → say "raises attack cost" or "defends against the threats listed in §2"
- ~~"detects BadUSB"~~ → say "catches unauthorized devices at the policy layer, including software-class HID injection — but acknowledges firmware-spoofing as a hardware mitigation"
- ~~"impossible to bypass"~~ → say "requires defeating N independent layers"

## If a demo fails mid-viva

1. Don't panic. Say: *"Let me restore the clean snapshot."*
2. VirtualBox Manager → Snapshots → `post-install-clean` → **Restore**.
3. ~30 seconds, you're back to a known good state.
4. Continue demo. Confidence > perfection.
