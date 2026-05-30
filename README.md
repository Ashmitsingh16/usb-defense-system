# USB Defense System

I built this as a coursework project to learn how Linux handles USB devices at the kernel level, and what it actually takes to block an unknown one before it can do anything. It runs on Rocky Linux 9 and only lets through USB devices I've explicitly added to a whitelist. Anything else gets blocked by USBGuard before the kernel binds a driver, and the screen locks until I clear it.

Current version is **0.2.0**.

## What it does

When a USB device is plugged in, the daemon checks its VID:PID:Serial against a signed whitelist.

- If the device is on the list, it mounts as normal.
- If it isn't:
  - USBGuard refuses to bind it to any driver.
  - A full-screen overlay grabs the keyboard and mouse and disables VT switching.
  - The alarm plays.
  - The event is written to an append-only file and to journald.

To clear the lockdown you need one of:

- A whitelisted USB marked as an unlock key.
- The admin password (argon2id-hashed, set during install).
- A 16-character paper recovery code (Crockford Base32, valid for one use only).

## What changed in 0.2.0

The previous version had a few things I wasn't happy with. Most of 0.2.0 was about fixing those:

- Whitelist tampering is now caught (HMAC-SHA256, fail-closed on mismatch).
- Admin auth moved from an env-var token to an argon2id-hashed password.
- Added the paper recovery code.
- The daemon runs as `Type=notify` with a 30-second watchdog and kernel-protect flags.
- The UI no longer writes the whitelist directly — everything goes through an IPC command that requires the password.

One gap I want to be upfront about: TTY-1 is still escapable. The block I added doesn't really stick because logind respawns gettys. It's a real issue and it's on the Phase 2 list.

## Install (Rocky / RHEL 9)

```bash
cd USB-Defense-Project/src
sudo ./scripts/install.sh
```

The installer ends with an interactive wizard that asks for an admin password (8 chars minimum) and prints the paper recovery code once. **Write it down before you continue** — that's the only time it's shown.

## Running it

```bash
sudo systemctl start usb-defense
sudo systemctl status usb-defense
usb-defense-py -m usbguard_defense.ui.main
```

## Tests

```bash
cd src
pip install -e .[dev]
python -m pytest usbguard_defense/tests -v
```

88 tests, with 4 skipped on Windows hosts (they need POSIX).

## Where things live

```
src/usbguard_defense/
├── daemon.py          # main loop + IPC dispatch
├── monitor.py         # pyudev USB watcher
├── whitelist.py       # whitelist + HMAC verify
├── usbguard_iface.py  # wraps the usbguard CLI
├── auth.py            # admin password (argon2id)
├── integrity.py       # HMAC sign/verify
├── recovery.py        # paper recovery code
├── tty_lockdown.py    # getty mask/unmask
├── ipc.py             # daemon ↔ UI socket
├── event_log.py       # append-only log
└── ui/                # PyQt5 frontend
```

Defaults and the hardened systemd unit are in `src/config/` and `src/systemd/`. Install/uninstall scripts live in `src/scripts/`.

## License

MIT. See `pyproject.toml`.
