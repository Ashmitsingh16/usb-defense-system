# USB Defense System

I built this to explore how Linux handles USB security at the kernel 
level — and what it actually takes to fully block and contain an 
unauthorized device before it can do anything. The motivation came 
from a real-world use case I can't share details of, but the 
implementation here is my own independent build.

It runs on Rocky Linux 9 and only lets through USB devices I've 
explicitly added to a whitelist. Anything else gets blocked by 
USBGuard before the kernel binds a driver, and the screen locks 
until I clear it.

Current version is **0.3.0**.

## What it does

When a USB device is plugged in, the daemon checks its VID:PID:Serial 
against a signed whitelist.

- If the device is on the list, it mounts as normal.
- If it isn't:
  - USBGuard refuses to bind it to any driver.
  - A full-screen overlay grabs the keyboard and disables VT switching 
    at every layer (X11 + systemd-logind + masked getty/autovt units).
  - The event is written to an append-only file and to journald.
  - Every subsequent tampering attempt during the lockdown is 
    timestamped and shown live on the lockdown screen and in the 
    Event Log.

To clear the lockdown you need one of:

- A whitelisted USB marked as an unlock key.
- The admin password (argon2id-hashed, set during install).
- A 16-character paper recovery code (Crockford Base32, valid for 
  one use only).

## What changed in 0.3.0

This release closes the TTY-1 gap that v0.2 admitted to, and adds 
the live intrusion-attempt timeline that the demo needed:

- **TTY-1 is no longer escapable.** Both `getty@tty1..6` and 
  `autovt@tty1..6` are masked at install time, and a 
  `systemd-logind` drop-in (`NAutoVTs=0`, `ReserveVT=0`) stops 
  logind from spawning a console even if a unit is unmasked by 
  hand. During an active lockdown the daemon also writes a runtime 
  drop-in under `/run/systemd/logind.conf.d/` and `SIGHUP`s logind 
  so the change takes effect immediately.
- **Live intrusion timeline on the lockdown screen.** Wrong admin 
  password, wrong recovery code, unauthorized USB re-insert, and 
  any change in the foreground virtual terminal 
  (`/sys/class/tty/tty0/active`) are all recorded with timestamps 
  and shown in a scrolling panel on the lockdown overlay. The same 
  events land in the append-only event log as `INTRUSION_ATTEMPT` 
  rows, so they survive a daemon restart.
- **Local-time formatting in the Event Log UI.** Event Log entries 
  are now rendered as `YYYY-MM-DD HH:MM:SS` in the operator's local 
  time zone, plus a new `Detail` column that surfaces the intrusion 
  reason inline (no need to open `events.log` by hand).
- **Lockdown state carries `started_at`.** The persistent lockdown 
  flag now records when the lockdown began, so a UI that reconnects 
  mid-lockdown shows the correct elapsed time and replays the 
  intrusion timeline from disk.
- **Brute-force throttle on the IPC socket.** After 5 failed 
  credential attempts (across `unlock_with_password`, 
  `unlock_with_seed`, `add_whitelist_entry`, `remove_whitelist_entry`, 
  `verify_password`) the daemon refuses further credentialed 
  commands for 60 s, doubling on every additional threshold breach. 
  Throttled attempts during lockdown are themselves logged as 
  `AUTH_LOCKED_OUT` intrusion attempts. Magic SysRq is also disabled 
  (`kernel.sysrq = 0`) so the kernel's emergency keyboard hotkeys 
  can't reclaim the keyboard from the X overlay.

## What changed in 0.2.0

The 0.2 release was about closing earlier integrity gaps:

- Whitelist tampering is caught (HMAC-SHA256, fail-closed on 
  mismatch).
- Admin auth moved from an env-var token to an argon2id-hashed 
  password.
- Added the paper recovery code.
- The daemon runs as `Type=notify` with a 30-second watchdog and 
  kernel-protect flags.
- The UI no longer writes the whitelist directly — everything goes 
  through an IPC command that requires the password.

## Install (Rocky / RHEL 9)

```bash
cd USB-Defense-Project/src
sudo
