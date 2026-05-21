# Changelog

All notable changes to **netwatch** are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions adhere
to SemVer.

## [0.1.0] — 2026-05-21

Initial release. Built as a deliberate, professional-grade replacement
for an earlier USB-defense codebase. See `docs/COMPARISON.md` for the
flaw-by-flaw contrast.

### Added

- Passive ARP-cache sensor (`/proc/net/arp` polling).
- Active ARP-scan sensor (scapy `srp()`).
- DHCP DISCOVER/REQUEST sniffer (scapy live capture).
- Baseline learning with JSON persistence and configurable learning window.
- nftables-based network freeze with SSH-session and loopback preservation.
- `ip link set <iface> down` fallback when nftables is unavailable.
- Bcrypt-hashed unlock password at `/etc/netwatch/auth.json` (mode 0640).
- 5-strike lockout on failed unlock attempts.
- Alert debounce window (5 s per MAC) to defeat plug/unplug DoS.
- Structured JSONL event log with `RotatingFileHandler` (size + count caps).
- Textual TUI with five tabs (Status / Devices / Alerts / Whitelist / Logs).
- `netwatch` CLI: `daemon`, `tui`, `status`, `setpassword`, `unlock`,
  `whitelist add|remove|list`, `baseline rebuild|show`, `version`.
- Hardened systemd unit with dedicated `netwatch` user, `CAP_NET_RAW` +
  `CAP_NET_ADMIN` capabilities only, `ProtectSystem=strict`, syscall filter.
- Headless `demo.py` that exercises every code path with mocked sensors
  and responder — runs on Windows.
- pytest suite, 76 tests, 87% coverage, mypy-strict-clean.

### Security

- All Ashmit USB-defense flaws #1, #2, #4, #5, #7, #10 addressed by design.
- See `docs/COMPARISON.md` for the per-flaw walkthrough.
