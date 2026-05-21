# netwatch

**Single-purpose LAN intrusion detection. Terminal-only. ~600 LOC.**

`netwatch` watches the wire for unknown devices. When a MAC it has never
seen before joins the LAN, it freezes the host's network, locks the
operator out, and shows the device's MAC / IP / vendor / interface in a
full-screen Textual TUI. Operator releases the lock by typing a
bcrypt-verified password. That's it. No GUI. No web dashboard. No
notifications-to-Slack. One job, done thoroughly.

This is a deliberate replacement for an earlier USB-defense codebase that
had grown to 2,495 LOC, ran as root, leaked its unlock token through
`/proc/<pid>/environ`, and shipped no daemon-level tests. `docs/COMPARISON.md`
walks through the contrast — and what we explicitly do *not* do.

---

## What it does

| Layer | How |
|---|---|
| Passive ARP-cache snoop | Parses `/proc/net/arp` every 5 s, diffs against baseline |
| Active ARP sweep | scapy `srp()` against the local /24 every 30 s |
| DHCP sniff | scapy live capture on UDP 67/68 — instant detection of DHCP DISCOVER/REQUEST |
| Baseline learning | First 90 s after start → silent enrollment, persisted as JSON |
| Response | nftables `inet netwatch` table with default-DROP on input/output; `lo` and the operator's active SSH session preserved |
| Lock | Daemon refuses to unfreeze until operator types the correct bcrypt-hashed password (5-strike lockout) |
| Log | JSONL at `/var/log/netwatch/events.log` via stdlib `RotatingFileHandler` |

## What it does NOT do

Honesty is part of the brand. `netwatch` does *not*:

- Defend against an attacker who already has root on the box. Once root,
  game's over — they can flush nftables, unmount the auth file, kill the
  daemon. `netwatch` is a tripwire, not a kernel-integrity monitor.
- Detect a passive eavesdropper that never speaks ARP or DHCP (e.g. a
  rogue mirror port). The threat model is "new endpoint joins the LAN,"
  not "wire tap."
- Block layer-2 attacks (ARP spoofing of an existing host). MAC-on-LAN
  hijacks are out of scope; we trust the first observation in learning mode.
- Run on Windows in production — only the test suite + TUI demo runs there.
  The daemon's freeze logic needs `nftables` + `CAP_NET_RAW`.

## Install

### Linux (Rocky 9 / Ubuntu 22+ / Debian 12)

```bash
sudo bash scripts/install.sh
```

The installer creates a system user `netwatch`, drops a default config to
`/etc/netwatch/netwatch.yaml`, prompts you for an unlock password
(bcrypt-hashed at `/etc/netwatch/auth.json`, mode 0640), and enables the
hardened systemd unit.

### Dev / test (any platform)

```bash
pip install -e ".[dev]"
pytest --cov=netwatch
python demo.py   # see scripted output
```

## Usage

```bash
netwatch daemon              # start in foreground
netwatch tui                 # daemon + interactive Textual TUI
netwatch status              # JSON snapshot
netwatch whitelist add aa:bb:cc:dd:ee:ff
netwatch whitelist list
netwatch baseline rebuild
netwatch setpassword
netwatch unlock              # verify your password (does not unlock a running daemon)
netwatch version
```

### TUI keys

| Key | Action |
|---|---|
| `s` `d` `a` `w` `l` | Switch to Status / Devices / Alerts / Whitelist / Logs |
| `b` | Rebuild baseline |
| `f` | Force freeze (manual lock) |
| `u` | Prompt for unlock password |
| `q` | Quit |
| `?` | Help |

## Architecture

```
sensors/  → arp-cache poll, active arp sweep, dhcp sniff
   ↓ (asyncio.Queue[Observation])
daemon/   → debounce, baseline lookup, alert
   ↓
responder → nftables INET netwatch table, preserves lo + SSH
   ↓
state     → locked + bcrypt-gated unlock
   ↓
events    → JSONL log, in-memory queue → TUI
```

The whole daemon takes injected `Baseline`, `Responder`, and `logger` — every
external side-effect is mockable. `tests/test_daemon.py` runs the full lock
→ unlock cycle without a single real subprocess.

## Threat model

**In scope.** A new physical or virtual device — laptop, phone, rogue VM,
test rig — joining the LAN that the host is on, without prior approval.

**Out of scope.** Local root attacker, kernel exploits, supply-chain
compromise of the netwatch binary itself, off-net surveillance.

**Trust assumptions.**

1. The bcrypt hash file at `/etc/netwatch/auth.json` is mode 0640, owned
   `root:netwatch`. If an attacker reads it, they still face bcrypt
   (cost 12 ≈ 250 ms/guess).
2. `nft` and `ip` are not symlink-hijacked. The systemd unit's
   `ProtectSystem=strict` + `NoNewPrivileges` raise that bar.
3. The first 90 s of operation are uncompromised. If an attacker is
   present during learning, their MAC enters the baseline; that's the
   nature of any whitelist system.

## License

MIT.
