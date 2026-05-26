# Demo Scenarios

Five scripted demonstrations for the final report and viva. Each one takes 2–5 minutes and produces clear screenshot-worthy evidence of the system working.

**Setup for every demo:**
- Rocky Linux VM running, post-install snapshot restored if needed.
- v0.2.0 setup wizard completed at install (admin password set, paper
  recovery code written down on paper).
- Daemon active: `sudo systemctl start usb-defense`.
- UI running: `usb-defense-py -m usbguard_defense.ui.main`.
- Live log open in a side terminal: `sudo journalctl -u usb-defense -f`.
- At least one authorized USB enrolled in the whitelist via the UI's
  password-gated Add Device dialog (marked `can_unlock=true`).
- One unauthorized USB ready to plug.

---

## Demo 1 — Authorized USB is allowed

**What it shows:** the happy path. Whitelisted devices mount transparently and are logged.

**Steps:**
1. Confirm dashboard reads `● SYSTEM SECURE` (green).
2. Plug your authorized USB into the host laptop.
3. VirtualBox menubar → **Devices → USB → [your USB]**.

**Expected:**
- Live log:
  ```
  USB event: add <vendor> <product> (<vid>:<pid>:<serial>)
  AUTHORIZED USB inserted: <label> (<fingerprint>)
  ```
- Dashboard's "Last event" line updates to "allowed: <label>".
- File manager opens the drive at `/run/media/<user>/<volume_label>`.

**Evidence to capture:** screenshot of dashboard + log terminal side-by-side, plus the file manager window showing the mounted drive.

---

## Demo 2 — Unauthorized USB triggers lockdown

**What it shows:** the core defense. An unknown USB is blocked at the kernel AND the user is locked out of the workstation.

**Steps:**
1. Have a **second** USB ready that is **NOT** on the whitelist.
2. Plug it into the host laptop.
3. VirtualBox menubar → **Devices → USB → [the unknown USB]**.

**Expected:**
- The screen flashes to a full-screen red overlay:
  ```
  ⚠  SYSTEM LOCKED  ⚠
  UNAUTHORIZED USB DEVICE DETECTED
  <Manufacturer> <Product>
  VID:PID = xxxx:yyyy   Serial = ...
  Class = MassStorage   USB = 2.10
  INSERT AUTHORIZED USB KEY TO UNLOCK
  ```
- Alarm sound loops.
- Keyboard and mouse input are swallowed by the overlay — you cannot click anything else.
- Live log:
  ```
  UNAUTHORIZED USB inserted: <vendor> <product>
  ENTERING LOCKDOWN due to <vid>:<pid>:<serial>
  Alarm started (pid=<n>) via aplay
  ```
- USBGuard refuses to authorize the device — `/dev/sdb` (or similar) does not appear:
  ```bash
  lsblk   # in a separate session, e.g. via SSH from host
  ```
  no new block device.

**Evidence to capture:** photo or screen-record of the red overlay, plus the log terminal showing the BLOCK + LOCKDOWN lines, plus `lsblk` proving no block device was bound.

---

## Demo 3 — Unlock key clears the lockdown

**What it shows:** the asymmetric trust model — only USBs flagged `can_unlock=true` clear a lockdown; regular authorized USBs do not.

### Option A — software simulator (no extra hardware needed)
Run each command from a separate non-locked terminal. **Note:** in v0.2.0
the `Ctrl+Alt+F<N>` TTY escape is deliberately blocked (that is in fact
Demo 6 below), so the practical option here is SSH from the host or
a second VM session opened *before* the lockdown is triggered.

```bash
# 1. Enter lockdown.
sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate lockdown

# 2. Insert a NORMAL authorized USB (can_unlock=false).
#    Expected: "authorized_insert" broadcast, overlay STAYS visible, alarm continues.
sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate authorized_normal

# 3. Insert the UNLOCK-KEY authorized USB (can_unlock=true).
#    Expected: "Lockdown cleared", overlay hides, alarm stops, dashboard green.
sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate authorized_key
```

### Option B — real hardware
Same flow with two physical USBs: one enrolled with `can_unlock=false`, the other with `can_unlock=true`. Plug them in sequence after triggering lockdown via Demo 2.

**Evidence to capture:**
- The journalctl tail showing all three events: lockdown_enter → authorized_insert (no clear) → authorized_insert + Lockdown cleared.
- Side-by-side screenshots of the overlay (still up after step 2; gone after step 3).

---

## Demo 4 — Paranoid restart (daemon-kill resilience)

**What it shows:** an attacker who kills the daemon mid-lockdown cannot just wait for systemd to restart it cleanly — the daemon re-enters lockdown from the persistent flag on disk.

**Steps:**
1. Trigger a lockdown (Demo 2, or use the simulator):
   ```bash
   sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate lockdown
   ```
2. With the overlay up, kill the daemon hard:
   ```bash
   sudo systemctl kill -s SIGKILL usb-defense
   ```
3. Wait ~1 second. systemd auto-restarts the service (v0.2.0: `Restart=always`, `RestartSec=1`, `WatchdogSec=30`). The restart should be near-instantaneous.
4. Check the daemon log:
   ```bash
   sudo journalctl -u usb-defense -n 20 --no-pager
   ```

**Expected:**
- The persistent flag file is still on disk:
  ```bash
  sudo cat /var/lib/usb-defense/lockdown.flag    # → "active"
  ```
- On restart, the daemon log shows:
  ```
  USB Defense daemon v0.2.0 starting
  Found persistent lockdown flag — entering lockdown on startup
  ```
- The lockdown state is restored: `self.locked = True` even though there was no fresh USB event.

**Why this matters:** without this, killing the daemon would silently dismiss the lockdown the next time it restarted. Now it doesn't.

**Evidence:** `cat` output of the flag file before and after the kill, plus the daemon log lines.

---

## Demo 5 — BadUSB / HID-injection scenario

**What it shows:** the policy ("everything not whitelisted is blocked") defends against the BadUSB class of attacks at the policy layer, even though software cannot detect firmware spoofing.

**Setup options (pick one):**

### Option A — Real hardware (most convincing)
Use a Rubber Ducky, Bash Bunny, or DIY Arduino Pro Micro flashed with a payload that types `xterm -e "echo HACKED > /tmp/pwned"` when enumerated as a keyboard.

### Option B — Software-emulated HID via the simulator
If you don't have the hardware, drive the running daemon directly:
```bash
# Fires an unauthorized_insert with device_class=HID-Keyboard
sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate badusb

# Then trigger the lockdown overlay for that device (the daemon broadcasts
# the unauthorized_insert above, but lockdown entry on a real insert is
# driven by the auto_block_unknown branch — replay it here for the demo).
sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate badusb_lockdown
```

**Expected:**
- Log: `UNAUTHORIZED USB inserted: Hak5 Rubber Ducky (1209:beef:DUCKY-PWN-001)`.
- Lockdown overlay appears.
- Alarm sounds.
- **Critically:** no payload is delivered. The HID device is blocked by USBGuard at the kernel BEFORE its keystrokes are routed to the input layer.

**Caveat to write up honestly:** if the BadUSB device spoofs the VID:PID:Serial of an *authorized* keyboard, it gets through. We acknowledge this in the threat model — hardware-validated USBs (IronKey class) are the only mitigation at procurement time.

**Evidence:** the log entry showing the HID device was caught, and `/tmp/pwned` does NOT exist on the filesystem (proving the payload never ran).

---

## Demo 6 — Admin-password unlock + TTY escape blocked (new in v0.2.0)

**What it shows:** the operator can recover from a lockdown without
needing the physical unlock-key USB, AND a curious attacker cannot
escape to a text console.

**Steps:**

1. Trigger lockdown via simulator:
   ```bash
   sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate lockdown
   ```
2. Press `Ctrl+Alt+F3` on the keyboard. **Nothing happens** — the X11
   `DontVTSwitch` option suppresses the VT switch entirely.
3. On the lockdown overlay, click **"Unlock with admin password"**.
4. Type the wrong password into the dialog → red text appears on the
   overlay: *"Wrong password — try again or use the paper code."*
5. Click the button again, enter the correct password.

**Expected:**
- Lockdown clears, overlay hides, dashboard turns green.
- Live log:
  ```
  UNLOCK_SUCCESS method=password
  Lockdown cleared: admin password
  ```
- Per-attempt audit trail: failed attempts log `UNLOCK_AUTH_FAILURE`.

**Evidence:** screenshot of the overlay with the inline error after a
wrong password, followed by the cleared dashboard. `journalctl -u
usb-defense` showing both the failure and the success line.

---

## Demo 7 — Paper recovery code unlock (new in v0.2.0)

**What it shows:** the worst-case recovery path — admin has lost every
unlock-key USB AND forgotten the password — and the code is invalidated
on use so it cannot be replayed.

**Steps:**

1. Have the paper recovery code on hand (the one written down during
   `setup.py`, or freshly generated via `setup.py --regenerate-recovery`).
2. Trigger lockdown:
   ```bash
   sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate lockdown
   ```
3. Click **"Unlock with paper recovery code"** on the overlay.
4. Type the 16-character code (hyphens optional, lowercase fine).

**Expected:**
- Lockdown clears.
- A warning dialog appears: *"The paper recovery code was used to clear
  this lockdown and has been INVALIDATED."*
- The hash file is deleted:
  ```bash
  sudo ls /etc/usb-defense/recovery_seed.hash    # → no such file
  ```
- Trying the same code a second time fails: the file is gone so verify
  returns False without even hitting the hash.

**Evidence:** screenshot of the consumed-code warning, plus the `ls`
output proving the hash file is gone, plus a second simulator run
showing the same code is now rejected.

---

## Demo 8 — Whitelist tamper detection (new in v0.2.0)

**What it shows:** a root user (or a misconfigured backup-restore script)
that hand-edits `/etc/usb-defense/whitelist.json` cannot insert hostile
entries silently — the daemon refuses to load any unsigned change.

**Steps:**

1. Confirm the daemon currently trusts the whitelist (status bar in UI
   does NOT say "tamper detected").
2. As root, hand-edit the whitelist file:
   ```bash
   sudo bash -c 'cat > /etc/usb-defense/whitelist.json <<EOF
   {
     "version": 1,
     "devices": [
       {
         "id": "hacker-1",
         "label": "Hacker USB",
         "vendor_id": "dead", "product_id": "beef",
         "serial": "EVIL", "device_class": "MassStorage",
         "added_by": "hacker", "added_at": "2026-01-01T00:00:00Z",
         "can_unlock": true
       }
     ]
   }
   EOF'
   ```
3. Restart the daemon:
   ```bash
   sudo systemctl restart usb-defense
   ```
4. Check the journal:
   ```bash
   sudo journalctl -u usb-defense -n 10 --no-pager
   ```

**Expected:**
- Log shows:
  ```
  Whitelist signature INVALID — possible tamper.
  Treating whitelist as empty (fail closed).
  WHITELIST TAMPER DETECTED on startup ...
  ```
- The hostile "dead:beef:EVIL" entry is NOT trusted: plug it in (or
  simulate it) → lockdown triggers.
- The UI status bar reads "Whitelist tamper detected — daemon refusing
  to load entries".
- `events.log` records a `WHITELIST_TAMPER` line.

**Recovery:** re-run setup with `--reset` (preserves entries, regenerates
key+sig), or manually re-sign by adding entries via the UI again.

**Evidence:** the journal lines proving fail-closed, the events.log
`WHITELIST_TAMPER` entry, and a screenshot of the UI status bar.

---

## Bonus mini-demos (if time allows)

### M1 — Audit log forensics
```bash
sudo cat /var/log/usb-defense/events.log | tail -20 | python3 -m json.tool
```
Show one JSON-line record per event, with full device fingerprint, timestamp, and action.

### M2 — Tamper-resistance of the event log
```bash
sudo lsattr /var/log/usb-defense/events.log
# expect "-----a----..." showing the append-only attribute
echo "rogue edit" | sudo tee -a /var/log/usb-defense/events.log    # appends OK
sudo sh -c 'echo "rogue" > /var/log/usb-defense/events.log'        # blocked
# → "Operation not permitted" even as root, unless attribute is removed first
```

### M3 — Daemon is unkillable in the way that matters
```bash
sudo systemctl kill usb-defense; sleep 6; sudo systemctl is-active usb-defense
# → active
```

### M4 — UI works offline
Stop the daemon. Open the UI. Confirm the whitelist manager still works, and the status bar reads "Daemon offline". (No enforcement when daemon is down, but the operator can still curate the whitelist.)

---

## Suggested order for the viva

1. Quick architecture diagram on a slide.
2. **Demo 1** (authorized) — establish baseline.
3. **Demo 2** (unauthorized → lockdown) — the headline.
4. **Demo 3 Part A** (can_unlock=false fails to unlock).
5. **Demo 3 Part B** (can_unlock=true clears).
6. **Demo 6** (admin password + TTY escape blocked) — shows auth-layer thinking.
7. **Demo 4** (paranoid restart) — shows defense-in-depth thinking.
8. **Demo 8** (whitelist tamper) — shows integrity-layer thinking.
9. **Demo 5** (BadUSB) — shows scope-aware thinking.
10. **M2** (append-only log) — shows tamper-resistance thinking.
11. **Demo 7** (paper recovery code) — shows recovery thinking, if time.

Total ≈ 20 minutes of demo, suitable for a 25-minute viva slot. If time
is tight, drop Demo 7 (the recovery code) — it's the lowest-frequency
real-world scenario and the easiest one to describe verbally.
