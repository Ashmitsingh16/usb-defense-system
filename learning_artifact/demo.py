"""Headless demo — runs the full daemon against fully-mocked sensors and
prints the operator-visible event stream + a snapshot of every TUI tab.

Use this on Windows / macOS to see what netwatch does without installing
scapy or running as root. Renders the same data the TUI shows; just without
the interactive widgets.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Sequence

from netwatch import auth
from netwatch.config import (
    BaselineConfig, Config, LoggingConfig, ResponderConfig, SensorConfig,
)
from netwatch.daemon import Daemon
from netwatch.responder import CommandResult, Responder
from netwatch.sensors import Observation


class _ScriptedRunner:
    """Records every command instead of running it. The output is the demo's
    proof that we *would* have applied the freeze on a real Linux host."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, args: Sequence[str]) -> CommandResult:
        self.calls.append(tuple(args))
        return CommandResult(args=tuple(args), returncode=0)


def _banner(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def _tui_status(d: Daemon) -> None:
    st = d.state.status_dict()
    print(f"[{'LOCKED' if st['locked'] else 'OK'}] uptime={st['uptime_seconds']}s  "
          f"baseline={st['baseline_size']}  alerts={st['alerts']}  "
          f"frozen={st['frozen']}  learning={st['learning']}")


def _tui_devices(d: Daemon) -> None:
    print(f"{'MAC':<22} {'Vendor':<24} {'Last IP':<16} {'Iface':<8} First seen")
    print("-" * 78)
    for dev in d.baseline.devices.values():
        print(f"{dev.mac:<22} {dev.vendor:<24} {(dev.last_ip or '-'):<16} {(dev.iface or '-'):<8} {dev.first_seen}")


def _tui_alerts(d: Daemon) -> None:
    print(f"{'Time':<10} {'MAC':<22} {'Vendor':<20} {'IP':<16} Source")
    print("-" * 78)
    for a in d.state.alerts:
        ts = time.strftime("%H:%M:%S", time.localtime(a.timestamp))
        print(f"{ts:<10} {a.mac:<22} {a.vendor:<20} {(a.ip or '-'):<16} {a.source}")


def _tui_logs(d: Daemon, n: int = 12) -> None:
    for ev in list(d.state.events)[-n:]:
        print(f"  {ev.timestamp}  {ev.type.value:<18} {ev.message}")


def main() -> int:
    workdir = Path("./.demo-state").resolve()
    workdir.mkdir(exist_ok=True)
    cfg = Config(
        sensors=SensorConfig(dhcp_sniff_enabled=False),
        responder=ResponderConfig(),
        baseline=BaselineConfig(learning_seconds=0, path=workdir / "baseline.json"),
        logging=LoggingConfig(dir=workdir / "logs", journald=False),
        auth_path=workdir / "auth.json",
        socket_path=workdir / "netwatch.sock",
    )
    # set demo password so unlock works
    auth.write_auth(cfg.auth_path, "demo")

    runner = _ScriptedRunner()
    responder = Responder(runner=runner, env={"SSH_CONNECTION": "203.0.113.5 51322 192.0.2.1 22"},
                          nft_available=lambda: True)
    logger = logging.getLogger("netwatch-demo")
    logger.addHandler(logging.NullHandler())

    daemon = Daemon(cfg, responder=responder, logger=logger)

    _banner("Scenario 1 -- learning mode (baseline_seconds=0 ⇒ already past)".replace("⇒", "=>"))
    # First, whitelist a couple of known devices to pretend we've baselined them.
    for mac in ["aa:bb:cc:00:00:01", "aa:bb:cc:00:00:02"]:
        daemon.add_whitelist(mac)
        daemon.handle_observation(Observation(mac, "10.0.0.10", "eth0", "arp-cache"))
    _tui_devices(daemon)

    _banner("Scenario 2 -- known device returns => no alert")
    daemon.handle_observation(Observation("aa:bb:cc:00:00:01", "10.0.0.10", "eth0", "arp-cache"))
    _tui_status(daemon)

    _banner("Scenario 3 -- UNKNOWN device joins LAN => INTRUDER + freeze + lock")
    daemon.handle_observation(Observation("b8:27:eb:de:ad:01", "10.0.0.99", "eth0", "dhcp"))
    _tui_status(daemon)
    print()
    print("nftables commands that would have been executed:")
    for c in runner.calls:
        print("  $ " + " ".join(c))

    _banner("Scenario 4 -- alerts pane")
    _tui_alerts(daemon)

    _banner("Scenario 5 -- bad unlock attempt")
    res = daemon.unlock("wrong-password")
    print(f"  unlock(wrong) -> ok={res.ok} reason={res.reason!r}  failed_unlocks={daemon.state.failed_unlocks}")

    _banner("Scenario 6 -- correct unlock releases freeze")
    res = daemon.unlock("demo")
    print(f"  unlock(demo) -> ok={res.ok}")
    _tui_status(daemon)

    _banner("Event log tail")
    _ = None  # noqa
    _tui_logs(daemon, n=14)

    print()
    print("Demo complete. State written to:", workdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
