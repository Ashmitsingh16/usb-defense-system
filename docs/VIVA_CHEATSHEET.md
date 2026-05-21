# Viva Cheat Sheet — print this and bring it

## 60-second pitch
*"Four-layer defense — kernel block via USBGuard, userspace policy daemon in Python, full-screen GUI lockdown with audible alarm, tamper-resistant audit log — that hardens a Rocky Linux 9 workstation against unauthorized USB devices. Uses an asymmetric trust model where regular authorized USBs can mount but only USBs explicitly marked as 'unlock keys' can clear a lockdown."*

## Numbers to drop into answers

| Metric | Value |
|---|---|
| Python files | **19** (10 daemon + 7 UI + 2 test) |
| Unit tests passing | **38 / 38** |
| Defense layers | **4** (kernel, daemon, UI, audit) |
| Daemon restart latency | **< 6 s** (systemd `RestartSec=5`) |
| USB → lockdown latency | **~300 ms** typical |
| Daemon idle RSS | **~30 MB** |
| Open network ports | **0** (Unix socket only) |
| Writable directories under sandbox | **3** (`/etc/usb-defense`, `/var/log/usb-defense`, `/var/lib/usb-defense`) |

## Top 10 anticipated questions — with prepared answers

**Q1. Why both USBGuard AND your own daemon?**
USBGuard is the *kernel enforcer*. Our daemon is the *policy + UX layer*: lockdown UI, alarm, the asymmetric `can_unlock` trust model, the persistent-flag paranoid restart, and the independent pyudev cross-check (defense in depth — a USBGuard bug doesn't blind us).

**Q2. What if I kill your daemon?**
systemd restarts within 5 s (`Restart=always`). On restart, the daemon reads `/var/lib/usb-defense/lockdown.flag` — if present, it re-enters lockdown immediately. Attacker would need to kill the daemon AND delete the flag AND stop systemd — all logged, all require root.

**Q3. BadUSB can spoof VID/PID/Serial. Doesn't that defeat you?**
Yes — and we *say so* in the threat model. Software cannot detect firmware spoofing. Mitigation is at procurement: hardware-validated USBs like IronKey. Our system raises attack cost (attacker needs exact authorized fingerprint AND a BadUSB controller) but cannot make it zero.

**Q4. What stops root from editing the whitelist?**
Nothing — root can do anything by definition. But: (a) file is `chmod 600`, (b) `auditd` can log changes, (c) signed whitelist is in `REPORT_OUTLINE.md` §8 as Phase-2 work. Within scope for an academic project.

**Q5. Why Python? Isn't it slow?**
The system bottleneck is human reaction (~250 ms) and audio latency, not Python overhead. Event-driven design means ~0% CPU idle, ~30 MB RAM. Python's iteration speed pays off — policy changes take minutes not hours.

**Q6. Why not D-Bus for IPC?**
Extra dependency, more complex, no advantage at this scale. Unix-domain socket + JSON lines is local-only (zero network attack surface), debuggable with `nc -U`, multiplexed for multiple UI clients.

**Q7. What about two USBs plugged at the same time, one authorized one not?**
**Strictest wins.** Unauthorized triggers lockdown regardless of the authorized USB also being present. Documented in `ARCHITECTURE.md` §9.

**Q8. The lockdown overlay uses Qt's `grabKeyboard`. Can't I just `Ctrl+Alt+F3` to a TTY?**
**Yes.** Honest answer. Software-only input grab is bypassable on X11. Real defense-grade needs Wayland compositor lock or a kernel input filter. Listed as known limitation in `REPORT_OUTLINE.md` §7.2.

**Q9. Why both journald AND a flat file for logging?**
Defense in depth for the audit trail itself. journald is queryable (`journalctl -u usb-defense -f`). The flat file uses `chattr +a` (append-only ext4 attribute) — even root cannot edit or delete without first removing the attribute, which itself is auditable. Two independent channels = attacker has to compromise both.

**Q10. What happens if the whitelist file is corrupted or malformed?**
Atomic-replace writes (`os.replace` after `.tmp`) prevent half-written files. If JSON is malformed, daemon logs the error and treats whitelist as empty — **fail-secure** (everything unauthorized) not fail-open.

## File pointer reference — what to open if asked

| If asked about… | Open this |
|---|---|
| Architecture overview | `docs/ARCHITECTURE.md` |
| "Show me the main daemon logic" | `src/usbguard_defense/daemon.py` (start at `_handle_insert`) |
| "How do you watch USB events?" | `src/usbguard_defense/monitor.py` (`_build_event`) |
| "Show me the lockdown UI" | `src/usbguard_defense/ui/lockdown.py` |
| "How is the alarm played?" | `src/usbguard_defense/alarm.py` (note `aplay` not `paplay`) |
| "Show me your tests" | `src/usbguard_defense/tests/` — 38 tests |
| "How does the install work?" | `src/scripts/install.sh` (8 steps) |
| "Show me the systemd hardening" | `src/systemd/usb-defense.service` |
| Schema of the whitelist | `src/config/whitelist.json` or `ARCHITECTURE.md` §7 |
| Threat model | `docs/ARCHITECTURE.md` §2 |
| Demo scripts | `docs/DEMO_SCENARIOS.md` |

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
