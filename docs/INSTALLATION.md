# Installation Guide

Step-by-step deployment of the USB Defense System on Rocky Linux 9.

## Prerequisites

- Rocky Linux 9 installed (via VM or bare metal)
- Internet connection (for `dnf install`)
- Root access (`sudo` works)

## Part 1: Inside Rocky Linux

### Step 1: Update the system

```bash
sudo dnf update -y
```

This may take a while on first boot. Reboot if a kernel update was applied:
```bash
sudo reboot
```

### Step 2: Install development tools

```bash
sudo dnf install -y git nano vim wget curl
```

### Step 3: Get the project source

If you have it on a Windows host and use shared folders:
```bash
# After mounting the shared folder
ls /media/sf_USB-Defense-Project/
```

Or clone from git (if you publish it there):
```bash
git clone https://github.com/yourusername/usb-defense.git
cd usb-defense
```

Or copy via USB / SCP / etc.

### Step 4: Run the installer

```bash
cd USB-Defense-Project/src
sudo ./scripts/install.sh
```

This installs:
- Python 3 + required pip packages (`PyQt5`, `pyudev`, `PyYAML`,
  `argon2-cffi`) in an isolated venv at `/usr/lib/usb-defense/venv/`
- USBGuard (kernel-level USB enforcement)
- Xorg server + GDM Wayland disable (v0.2.0: lockdown grab is X11-only)
- `/etc/X11/xorg.conf.d/99-usbdefense-novtswitch.conf` (blocks Ctrl+Alt+F<N>)
- The defense daemon as a hardened systemd service (notify-type,
  Restart=always, watchdog 30 s, kernel-protect flags)
- The PyQt5 UI as an autostart application

**Final step is interactive (v0.2.0 setup wizard):**

1. Choose an admin password (8 chars minimum, typed twice).
2. Write down the 16-character paper recovery code displayed in the
   banner — **shown exactly once.** Lock it in a drawer with your keys.

If the wizard is interrupted, re-run it standalone:

```bash
sudo /usr/lib/usb-defense/venv/bin/python ./scripts/setup.py
```

### Step 5: Generate the alarm sound

```bash
sudo /usr/lib/usb-defense/venv/bin/python \
  /path/to/USB-Defense-Project/src/scripts/generate_alarm.py \
  /usr/lib/usb-defense/assets/alarm.wav
```

Replace `/path/to/...` with where you copied the project. (Or write your own `alarm.wav` and place it there.)

### Step 6: Add your authorized USBs to the whitelist

Plug in each USB you want to authorize. Then find its details:

```bash
lsusb -v 2>/dev/null | grep -E "idVendor|idProduct|iSerial" | head -20
```

You'll see something like:
```
idVendor       0x0951 Kingston Technology
idProduct      0x1666 DataTraveler 100 G3/G4/SE9 G2
iSerial        3 60A44C413FAEE2B129C9015A
```

Open the UI:
```bash
usb-defense-py -m usbguard_defense.ui.main
```

Click **Manage Whitelist** → **+ Add Device**, fill in:
- Label: a friendly name like "Admin Backup Drive"
- Vendor ID: `0951` (without `0x`)
- Product ID: `1666`
- Serial: `60A44C413FAEE2B129C9015A`
- Class: `MassStorage`
- Tick **"This USB can unlock the system from lockdown"** if you want it to be a key

Click OK. **A password prompt appears** (v0.2.0). Enter the admin password
you chose during install. The daemon verifies the password, signs the
updated whitelist, and the entry appears in the list.

Repeat for each authorized USB. Wrong-password attempts are logged to
`/var/log/usb-defense/events.log` as `AUTH_FAILURE` events.

### Step 7: Start the daemon

```bash
sudo systemctl start usb-defense
sudo systemctl status usb-defense
```

Expected output should show `active (running)` and recent log lines.

### Step 8: Test it

In a terminal, watch the live log:
```bash
sudo journalctl -u usb-defense -f
```

In another terminal, plug in:
- An authorized USB → log says AUTHORIZED, no alarm, drive mounts
- An unrecognized USB → log says UNAUTHORIZED, alarm sounds, lockdown screen appears
- The authorized "unlock key" USB while locked → lockdown clears

## Troubleshooting

### "Permission denied" when running install.sh
You forgot `sudo`. Run:
```bash
chmod +x ./scripts/install.sh
sudo ./scripts/install.sh
```

### Daemon won't start
```bash
sudo journalctl -u usb-defense --no-pager | tail -30
```
Look for Python tracebacks. Common cause: missing dependency in the venv.

### USBGuard not blocking devices
Verify USBGuard is running:
```bash
sudo systemctl status usbguard
sudo usbguard list-devices
```

### Lockdown overlay doesn't appear
The UI must be running for the visual overlay. The daemon will still log + block, but you won't see the red lockdown screen unless the UI process is alive.

Run it (as your normal user, NOT root):
```bash
usb-defense-py -m usbguard_defense.ui.main
```

### No alarm sound
Make sure `alarm.wav` exists at `/usr/lib/usb-defense/assets/alarm.wav` and `paplay` is installed:
```bash
ls -la /usr/lib/usb-defense/assets/
which paplay
sudo dnf install pulseaudio-utils
```

### Want to undo everything
```bash
sudo ./scripts/uninstall.sh
```

## What got installed where

| Path | What it is |
|---|---|
| `/usr/lib/usb-defense/` | Source code + virtualenv |
| `/etc/usb-defense/config.yaml` | Main settings |
| `/etc/usb-defense/whitelist.json` | Authorized devices |
| `/etc/systemd/system/usb-defense.service` | systemd unit |
| `/var/log/usb-defense/events.log` | Append-only event log |
| `/run/usb-defense/` | Runtime sockets, pidfile |
| `/var/lib/usb-defense/` | Persistent lockdown state |
| `/etc/xdg/autostart/usb-defense-ui.desktop` | UI autostart |
| `/etc/usbguard/rules.conf` | USBGuard kernel rules |
