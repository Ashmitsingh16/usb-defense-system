# Deployment Runbook

The click-by-click guide for the steps that only you can do. Code is ready, alarm sound is generated, ISO is downloaded — this document gets it all running inside Rocky Linux.

Estimated total time: **~60 minutes** (most of it waiting for Rocky's installer to copy files).

---

## Phase A — Boot Rocky Linux in the VM (~5 min)

### A.1 Attach the ISO to the VM

1. Open **Oracle VirtualBox Manager**.
2. Right-click the **Rocky-Defense** VM → **Settings…** → **Storage**.
3. In the **Storage Devices** tree, click the empty optical drive under "Controller: IDE" or "Controller: SATA".
4. On the right, click the small disc icon next to "Optical Drive" → **Choose a disk file…**
5. Navigate to `C:\Users\KIIT\Desktop\USB-Defense-Project\ISOs\Rocky-9-latest-x86_64-dvd.iso` and pick it.
6. Click **OK**.

### A.2 Configure boot order (one-time)

1. Settings → **System** → **Motherboard** tab.
2. In **Boot Order**, drag **Optical** above **Hard Disk**. (You'll undo this after install.)
3. Click **OK**.

### A.3 Start the VM

1. Select the VM, click **Start** (green arrow).
2. A black screen appears with the Rocky boot menu.
3. Use ↑/↓ arrows to highlight **"Install Rocky Linux 9"**, press **Enter**.
4. Wait ~30s for the installer GUI to load.

---

## Phase B — Install Rocky Linux (~30 min, mostly file copy)

When the **WELCOME TO ROCKY LINUX** screen appears:

### B.1 Language and keyboard

1. **English (United States)** → **Continue**.

### B.2 Installation Summary screen

You'll see a grid of orange-highlighted icons. Click each in order:

#### Time & Date
1. Click **Time & Date**.
2. Region: **Asia**, City: **Kolkata** (or wherever you are).
3. Toggle **Network Time** ON.
4. Click **Done** (top-left).

#### Software Selection
1. Click **Software Selection**.
2. **Base Environment:** select **"Workstation"** (gives you a GNOME desktop).
3. **Additional software:** tick **"Development Tools"** and **"Headless Management"**.
4. Click **Done**.

#### Installation Destination
1. Click **Installation Destination**.
2. You should see the **30 GB VBOX HARDDISK** with a checkmark.
3. **Storage Configuration:** leave as **Automatic**.
4. Click **Done**. (Don't tick Encryption — adds complexity not needed for this project.)

#### Network & Host Name
1. Click **Network & Host Name**.
2. Toggle the **Ethernet (enp0s3)** switch to **ON** (top-right).
3. **Host Name:** type `rocky-defense`, click **Apply**.
4. Click **Done**.

#### Root Password
1. Click **Root Password**.
2. Pick a strong password. Tick **"Lock root account"** if you want to be safe; you'll use `sudo` from the user account anyway.
3. **Don't tick** "Allow root SSH login with password" — security hygiene.
4. Click **Done** twice if it warns about the password.

#### User Creation
1. Click **User Creation**.
2. **Full name:** Your name.
3. **User name:** something short and lowercase, e.g., `ratnesh`.
4. **Tick** "Make this user administrator" (gives sudo).
5. Set a password.
6. Click **Done**.

### B.3 Begin Installation

1. The orange warning icons should all be gone now.
2. Click **Begin Installation** (bottom-right).
3. Wait ~15–25 minutes. Files copy, package install runs.
4. When done, click **Reboot System**.

### B.4 First boot — initial setup

1. VM reboots. **Eject the ISO now** to avoid booting into the installer again:
   - In the VirtualBox menubar (while VM is focused): **Devices → Optical Drives → Remove disk from virtual drive**.
2. GRUB boot menu — let the default highlight (Rocky Linux) auto-select, or press Enter.
3. **License Information:** click it, tick **"I accept the license agreement"**, **Done**.
4. Click **Finish Configuration**.
5. GNOME first-run wizard:
   - Language → Next
   - Keyboard → Next
   - Privacy: turn Location off if you want → Next
   - Online Accounts → **Skip**
   - **Start Using Rocky Linux** → big window closes; you land on the desktop.

You're in.

---

## Phase C — Prep Rocky for the project (~10 min)

### C.1 Update Rocky

Open **Terminal** (Activities → Terminal or right-click desktop → Open Terminal).

```bash
sudo dnf update -y
```

Enter your user password when prompted. This may pull 200–500 MB of updates. Reboot if a kernel update came down:

```bash
sudo reboot
```

### C.2 Install VirtualBox Guest Additions (enables shared folder)

The cleanest way to move the project files from Windows into Rocky is a shared folder.

In Rocky's terminal:

```bash
sudo dnf install -y epel-release
sudo dnf install -y kernel-devel kernel-headers gcc make perl elfutils-libelf-devel bzip2 tar
```

Then in the VirtualBox menubar (while VM is focused): **Devices → Insert Guest Additions CD image…**

When the autorun prompt asks to run the installer, click **Run**, enter your password. Wait ~3 min. When it says "Press Return to close this window", press Enter.

```bash
sudo reboot
```

### C.3 Set up the shared folder

1. **Shut down** Rocky cleanly (gear icon → Power Off).
2. In VirtualBox Manager: select **Rocky-Defense** → **Settings…** → **Shared Folders**.
3. Click the small **+** icon on the right.
4. **Folder Path:** `C:\Users\KIIT\Desktop\USB-Defense-Project`
5. **Folder Name:** `USB-Defense-Project`
6. Tick **Auto-mount** and **Make Permanent**.
7. **Mount point:** `/mnt/usb-defense-project`
8. Click **OK**, **OK**.
9. Boot Rocky back up.
10. Add your user to the `vboxsf` group so you can read the share:
    ```bash
    sudo usermod -aG vboxsf $USER
    ```
11. **Log out and log back in** (so the group takes effect). Easiest: reboot.
12. Verify:
    ```bash
    ls /mnt/usb-defense-project
    # You should see: README.md  docs  src  ISOs  Downloads  VMs  WHEN_YOU_RETURN.md
    ```

---

## Phase D — Install the USB Defense System (~5 min)

### D.1 Run the installer

```bash
# Shared-folder mount point on this VM is /media/sf_USB-Defense-Project
# (per the 2026-05-21 sync session). If yours is different, adjust the path.
cd /media/sf_USB-Defense-Project/src
sudo ./scripts/install.sh
```

The installer runs nine numbered steps. The final step (`Step 9/9: First-run
setup ceremony`) is **interactive** as of v0.2.0:

1. Prompts for an admin password twice (8 chars minimum).
2. Prints a 16-character paper recovery code in a banner. **Write this
   down on paper now — it is displayed exactly once.** Press Enter when
   the code is on paper.

If you accidentally interrupt the wizard (Ctrl+C, network drop, etc.) you
can re-run just the wizard without re-installing the daemon:

```bash
sudo /usr/lib/usb-defense/venv/bin/python \
  /media/sf_USB-Defense-Project/src/scripts/setup.py
```

To rotate the paper code (e.g., if it has been used or compromised):

```bash
sudo /usr/lib/usb-defense/venv/bin/python \
  /media/sf_USB-Defense-Project/src/scripts/setup.py --regenerate-recovery
```

Watch for any red errors during the install proper. Expected final output:

```
================================================================
  USB Defense System installed successfully!
  ...
================================================================
```

### D.2 Install the alarm sound

The installer copies `src/assets/alarm.wav` into `/usr/lib/usb-defense/assets/` automatically (since I already generated it on Windows). Verify:

```bash
ls -la /usr/lib/usb-defense/assets/
# expect: alarm.wav (≈ 172 KB)
```

If it's missing for any reason, regenerate it inside Rocky:

```bash
sudo /usr/lib/usb-defense/venv/bin/python \
  /mnt/usb-defense-project/src/scripts/generate_alarm.py \
  /usr/lib/usb-defense/assets/alarm.wav
```

### D.3 Start the daemon

```bash
sudo systemctl start usb-defense
sudo systemctl status usb-defense
# expect: Active: active (running)
```

If it shows "failed", read the log:

```bash
sudo journalctl -u usb-defense -n 50 --no-pager
```

### D.4 Launch the UI

```bash
usb-defense-py -m usbguard_defense.ui.main
```

The dark-themed dashboard should appear. Status line should read "Connected to daemon". If it says "Daemon offline", the daemon's IPC socket isn't ready — wait 2s and try again.

---

## Phase E — Verify it actually works (~10 min)

### E.1 First sanity test — UI lockdown without real hardware

With both daemon and UI running, open a **second terminal**:

```bash
sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate lockdown
```

The lockdown overlay should slam onto your screen with the red "SYSTEM LOCKED" banner and the alarm should start.

To clear it:

```bash
sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate unlock
```

### E.2 Plug in a real USB

Plug a USB stick into your laptop's port.

VirtualBox needs to forward it: **Devices → USB → [pick your USB stick]** in the VM menubar.

Watch the daemon log live in a terminal:

```bash
sudo journalctl -u usb-defense -f
```

Expected entries:

```
USB event: add Kingston DataTraveler 3.0 (0951:1666:60A44C413...)
UNAUTHORIZED USB inserted: Kingston DataTraveler 3.0 (...)
ENTERING LOCKDOWN due to 0951:1666:60A44C413...
```

The lockdown overlay should appear.

### E.3 Authorize that USB and try again

Force-unlock first (you're testing):

```bash
sudo /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.tests.simulate unlock
```

Get the USB's real VID/PID/Serial. With the USB still inserted into the VM:

```bash
lsusb -v 2>/dev/null | grep -E "idVendor|idProduct|iSerial" | head -20
```

Copy the values. In the UI: **Manage Whitelist → + Add Device**, fill in the label, VID (just the 4 hex digits, no `0x`), PID, Serial, Class (`MassStorage` for a thumb drive). Tick **"This USB can unlock the system from lockdown"** if you want it to act as a key. **Save.**

Pull the USB out of the VM (Devices → USB → untick it). Plug it back in.

Expected log:
```
AUTHORIZED USB inserted: My USB (0951:1666:...)
```

No lockdown. Drive auto-mounts under `/run/media/<user>/`.

---

## Phase F — Snapshot the VM (1 min, do this NOW)

Before doing anything risky:

1. VirtualBox Manager → right-click **Rocky-Defense** → **Snapshots**.
2. **Take Snapshot…**
3. Name: `post-install-clean`.
4. Description: `Rocky 9 + USB-Defense installed and verified.`
5. **OK.**

If something breaks later, **Restore** this snapshot — instant rewind.

---

## Phase G — Pick your Qt platform: Wayland vs X11

Rocky 9's GNOME defaults to Wayland. The daemon works on either, but the
lockdown overlay's input-grabbing behaviour does not:

| Platform | Overlay renders | Alarm plays | Input grab |
|---|---|---|---|
| `wayland` (default) | yes | yes | **no** — overlay is bypassable by switching windows |
| `xcb` (X11) | yes | yes | **yes** — `grabKeyboard()` / `grabMouse()` work |

Wayland's design intentionally forbids regular windows from grabbing
keyboard/mouse globally (only `xdg_popup` surfaces may), which is the
right behaviour for everyday application security but defeats our
lockdown overlay. If you want the demo to actually lock the operator
out of the desktop, switch the UI to X11.

### G.1 Install the X11 backend libraries

```bash
sudo dnf install -y \
    libxcb xcb-util xcb-util-image xcb-util-keysyms \
    xcb-util-renderutil xcb-util-wm xcb-util-cursor \
    libxkbcommon-x11
```

### G.2 Launch the UI under X11

```bash
cd /usr/lib/usb-defense
export QT_QPA_PLATFORM=xcb
./venv/bin/python -m usbguard_defense.ui.main
```

If Qt complains about "could not connect to display", you are inside a
pure-Wayland GNOME session and need to log out, choose **"GNOME on
Xorg"** at the GDM login screen, then log back in. Then the UI runs
under X11 and the lockdown overlay grabs input as intended.

### G.3 Persist the choice

To make X11 the default for the UI without touching the user shell
profile, edit `/etc/systemd/user/usb-defense-ui.service` (if you wired
it up as a user service) or the `.desktop` autostart file at
`/etc/xdg/autostart/usb-defense-ui.desktop` and prepend the env var:

```
Exec=env QT_QPA_PLATFORM=xcb /usr/lib/usb-defense/venv/bin/python -m usbguard_defense.ui.main
```

### G.4 What the report should say

If you keep the Wayland demo, document the limitation honestly in §7.2
of the report (the WAY-1 caveat is already written for you). If you
switch to X11, you can claim full input-grab in §6.1 Demo 2 — but you
should still mention Wayland as a documented next-step for production
hardening.

---

## You're done

The system is live. Next steps (separate documents):
- `DEMO_SCENARIOS.md` — scripted demos for your report
- `REPORT_OUTLINE.md` — the academic report skeleton
- `REPORT.md` — the full first-pass academic report

If you hit a wall at any step, tell me which step number and what the error said.
