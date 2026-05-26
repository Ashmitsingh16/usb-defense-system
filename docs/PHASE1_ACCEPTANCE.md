# Phase 1 — VM Acceptance Checklist

Run this end-to-end inside the Rocky VM. It's the only remaining task before
we can tag `v0.2.0`. Estimated time: 30 minutes.

You can stop and resume between sections. If anything fails, copy the
`journalctl -u usb-defense -n 50` output and we'll diagnose it.

## A. Sync new code into the VM

From a host PowerShell:

```powershell
# Confirm Windows-side tests still pass before sync.
cd C:\Users\KIIT\Desktop\USB-Defense-Project\src
python -m pytest usbguard_defense/tests -q
# Expect: 82 passed, 4 skipped
```

From inside the VM (terminal):

```bash
sudo rsync -av --delete \
  /media/sf_USB-Defense-Project/src/usbguard_defense/ \
  /usr/lib/usb-defense/usbguard_defense/

sudo rsync -av \
  /media/sf_USB-Defense-Project/src/scripts/ \
  /media/sf_USB-Defense-Project/src/systemd/ \
  /media/sf_USB-Defense-Project/src/config/ \
  /tmp/usb-defense-update/

# Re-run installer to pick up the new systemd unit, X11 config, deps:
sudo bash /media/sf_USB-Defense-Project/src/scripts/install.sh
```

The installer will end with the **setup wizard**. When it prompts:

- Enter an admin password (twice). Pick something you'll remember — 8 chars
  minimum. *Write it on the same paper as the recovery code.*
- Read the paper recovery code aloud while writing it down. Verify each
  character — Crockford Base32 has no `I`, `L`, `O`, `U` to confuse with
  `1`, `0`, `V`.
- Press Enter once written.

If the installer fails mid-wizard, re-run just the wizard:

```bash
sudo /usr/lib/usb-defense/venv/bin/python \
  /media/sf_USB-Defense-Project/src/scripts/setup.py
```

**v0.2.0 socket-permissions caveat:** The installer added your user
(`SUDO_USER`) to the new `usbdefense` group, but Linux only picks up
group membership at login time. After install, **log out of the
desktop and log back in** before running the UI — otherwise the UI
will see "Daemon offline" because it can't connect to the now-0660
socket. Verify with:

```bash
groups
# expect: ... usbdefense ...
```

If `usbdefense` isn't in your groups even after relog, run it manually:

```bash
sudo usermod -a -G usbdefense "$USER"
# then log out + back in
```

## B. Restart and verify daemon

```bash
sudo systemctl daemon-reload
sudo systemctl restart usb-defense
sudo systemctl status usb-defense
# Expect: active (running), no errors. The Watchdog line should show
# a recent timestamp (proves WATCHDOG=1 is reaching systemd).
```

Then check journal:

```bash
sudo journalctl -u usb-defense -n 30 --no-pager
# Look for "USB Defense daemon v0.2.0 starting" and "Daemon ready".
# WHITELIST_TAMPER would appear here if something is wrong.
```

## C. Launch UI and confirm baseline

```bash
# Wayland → X11 transition: log out of GNOME and log back in. On the
# greeter, click the gear icon, choose "GNOME on Xorg". (This is the
# session that DontVTSwitch and grabKeyboard actually work in.)
# If the greeter still defaults to Wayland, check /etc/gdm/custom.conf
# for WaylandEnable=false.

# In a terminal:
echo $XDG_SESSION_TYPE
# Expect: x11

cd /usr/lib/usb-defense
./venv/bin/python -m usbguard_defense.ui.main
```

Confirm:

- [ ] Dashboard shows "Connected to daemon".
- [ ] Whitelist Manager tab loads empty (we wiped to start fresh).
- [ ] Status bar does NOT show "tamper detected".

## D. Add a device with password gate

In the UI:

1. Whitelist Manager → **+ Add Device**.
2. Fill in any test entry (use the values from `lsusb -v` for a real USB,
   or make some up like `vendor_id=0000`, `product_id=0000`,
   `serial=TEST001`, `device_class=MassStorage`).
3. Tick "This USB can unlock the system from lockdown" — we want at least
   one unlock-key in the whitelist.
4. Click OK.
5. **Password prompt appears.** Try entering the wrong password first →
   expect "Wrong admin password" error.
6. Now enter the correct password → "Device added to whitelist." appears.
7. The entry shows up in the list with `[UNLOCK KEY]` next to it.

```bash
# In another terminal:
sudo cat /etc/usb-defense/whitelist.json | head
sudo ls -l /etc/usb-defense/whitelist.sig
# Both should exist, both 0600 root:root.
```

## E. Trigger lockdown via simulator

```bash
sudo /usr/lib/usb-defense/venv/bin/python \
  -m usbguard_defense.tests.simulate lockdown
```

Confirm:

- [ ] Red lockdown overlay appears full-screen.
- [ ] Alarm plays (if speakers / audio is configured).
- [ ] **Press `Ctrl+Alt+F3`** — should do nothing (DontVTSwitch is set).
- [ ] Press random keys — overlay does not let them through.
- [ ] Two new buttons visible: "Unlock with admin password" and
      "Unlock with paper recovery code".

## F. Unlock with admin password

1. On the locked overlay, click **Unlock with admin password**.
2. Dialog appears, accepts text input (keyboard grab released).
3. Type a wrong password → error appears on the overlay:
   *"Wrong password — try again or use the paper code."*
4. Click the button again, enter the correct password → lockdown clears,
   dashboard turns green.

## G. Lockdown again, unlock with paper code

```bash
sudo /usr/lib/usb-defense/venv/bin/python \
  -m usbguard_defense.tests.simulate lockdown
```

1. Click **Unlock with paper recovery code**.
2. Type the 16-character code (hyphens optional, lowercase ok).
3. Lockdown clears. A warning dialog appears:
   *"The paper recovery code was used to clear this lockdown and has
   been INVALIDATED."*

Verify the code is now consumed:

```bash
sudo ls -l /etc/usb-defense/recovery_seed.hash
# Should not exist anymore.
```

Generate a new one:

```bash
sudo /usr/lib/usb-defense/venv/bin/python \
  /media/sf_USB-Defense-Project/src/scripts/setup.py \
  --regenerate-recovery
# Write down the new code, press Enter.
```

## H. Tamper test — hand-edit the whitelist

```bash
# Add a hostile entry as root, bypassing the daemon:
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

sudo systemctl restart usb-defense
sudo journalctl -u usb-defense -n 10 --no-pager
# Expect: "Whitelist signature INVALID — possible tamper. Treating
# whitelist as empty (fail closed)."

# And the event log should record the tamper:
sudo cat /var/log/usb-defense/events.log | tail -5 | grep TAMPER
# Expect: a WHITELIST_TAMPER line.
```

Now confirm that the hostile entry is NOT active — simulate insertion of
its VID:PID:Serial:

```bash
sudo /usr/lib/usb-defense/venv/bin/python -c "
from usbguard_defense.ipc import IPCClient
c = IPCClient()
c.connect()
c.send_command({
    'cmd': 'simulate_event',
    'event': {
        'type': 'lockdown_enter',
        'offender': {'vendor_id': 'dead', 'product_id': 'beef',
                     'serial': 'EVIL', 'manufacturer': 'Hacker',
                     'product': 'Evil USB', 'device_class': 'MassStorage'},
    },
})
"
# Overlay should appear — confirming the daemon refused to trust the
# tampered whitelist. Recovery: clear the lockdown via paper code or
# admin password, then re-run the setup wizard's --reset to rebuild
# trust:
sudo /usr/lib/usb-defense/venv/bin/python \
  /media/sf_USB-Defense-Project/src/scripts/setup.py --reset
```

## I. Confirm production switch is documented (not flipped — viva needs the simulator)

```bash
sudo grep simulator_enabled /etc/usb-defense/config.yaml
# expect: simulator_enabled: true   (so demos 3, 5, 6, 7, 8 work)
```

For the viva, leave it `true`. For a real pilot deployment, flip to
`false` and `sudo systemctl restart usb-defense`. This is documented in
`SECURITY.md` under "Production-deployment switch".

## J. Wrap up

If A–I all pass:

```bash
cd /media/sf_USB-Defense-Project
git add -A
git status
# Review the changes — should match the CHANGELOG 0.2.0 list.
```

Then on the Windows host:

```powershell
cd C:\Users\KIIT\Desktop\USB-Defense-Project
git tag -a v0.2.0 -m "Phase 1 security hardening"
# git push origin main --tags    (only if you have a remote)
```

## What to tell your senior

> "v0.2.0 closes the auth and tamper gaps we identified in v0.1.4. Whitelist
> edits now require an admin password, the whitelist file is HMAC-signed
> so accidental or unauthorised hand-edits are caught at load time and
> trigger a fail-closed mode, the lockdown overlay can no longer be
> escaped via TTY switching, and there's a paper-recovery code so a lost
> unlock-USB is no longer a brick scenario. Threat model and limits are
> documented in `docs/PHASE1_DESIGN.md`. The system is ready for a
> 1–3 machine pilot."

## If something fails

Run this once and paste the output:

```bash
sudo systemctl status usb-defense
sudo journalctl -u usb-defense -n 100 --no-pager
sudo ls -l /etc/usb-defense/
```

That's enough for me (or you) to figure out what went wrong.
