"""Single CLI entry point: `netwatch <subcommand>`."""
from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from netwatch import __version__, auth
from netwatch.baseline import Baseline
from netwatch.config import Config, load_config


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="netwatch", description="LAN intrusion detection daemon")
    p.add_argument("--config", type=Path, default=None, help="path to netwatch.yaml")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("daemon", help="run the detection daemon in the foreground")
    sub.add_parser("tui", help="run the daemon with the interactive TUI attached")
    sub.add_parser("unlock", help="unlock a locked daemon (prompts for password)")
    sub.add_parser("status", help="print current daemon status as JSON and exit")
    sub.add_parser("version", help="print version")

    sp_pw = sub.add_parser("setpassword", help="set the unlock password (bcrypt-hashed)")
    sp_pw.add_argument("--from-stdin", action="store_true", help="read password from stdin (no prompt)")

    sp_wl = sub.add_parser("whitelist", help="manage the MAC whitelist")
    wl_sub = sp_wl.add_subparsers(dest="wl_command", required=True)
    wl_add = wl_sub.add_parser("add"); wl_add.add_argument("mac")
    wl_rm  = wl_sub.add_parser("remove"); wl_rm.add_argument("mac")
    wl_sub.add_parser("list")

    sp_bl = sub.add_parser("baseline", help="manage the device baseline")
    bl_sub = sp_bl.add_subparsers(dest="bl_command", required=True)
    bl_sub.add_parser("rebuild")
    bl_sub.add_parser("show")
    return p


# ---------------------------------------------------------------- subcommands
def _cmd_version(_cfg: Config, _args: argparse.Namespace) -> int:
    print(f"netwatch {__version__}")
    return 0


def _cmd_setpassword(cfg: Config, args: argparse.Namespace) -> int:
    if args.from_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("Set unlock password: ")
        confirm = getpass.getpass("Confirm:               ")
        if password != confirm:
            print("passwords do not match", file=sys.stderr)
            return 2
    if not password:
        print("empty password rejected", file=sys.stderr)
        return 2
    rec = auth.write_auth(cfg.auth_path, password)
    print(f"auth written to {cfg.auth_path} (created {rec.created})")
    return 0


def _cmd_whitelist(cfg: Config, args: argparse.Namespace) -> int:
    baseline = Baseline.load(cfg.baseline.path, learning_seconds=cfg.baseline.learning_seconds)
    if args.wl_command == "add":
        try:
            baseline.add_whitelist(args.mac)
        except ValueError as exc:
            print(f"invalid mac: {exc}", file=sys.stderr); return 2
        baseline.save(); print(f"whitelisted {args.mac.lower()}"); return 0
    if args.wl_command == "remove":
        try:
            ok = baseline.remove_whitelist(args.mac)
        except ValueError as exc:
            print(f"invalid mac: {exc}", file=sys.stderr); return 2
        baseline.save()
        if not ok:
            print(f"{args.mac.lower()} not in whitelist", file=sys.stderr); return 1
        print(f"removed {args.mac.lower()}"); return 0
    if args.wl_command == "list":
        for mac in sorted(baseline.whitelist):
            print(mac)
        return 0
    return 2


def _cmd_baseline(cfg: Config, args: argparse.Namespace) -> int:
    baseline = Baseline.load(cfg.baseline.path, learning_seconds=cfg.baseline.learning_seconds)
    if args.bl_command == "rebuild":
        baseline.reset_learning(); baseline.save()
        print("baseline cleared; restart the daemon to relearn"); return 0
    if args.bl_command == "show":
        out = {m: d.to_dict() for m, d in baseline.devices.items()}
        print(json.dumps(out, indent=2)); return 0
    return 2


def _cmd_daemon(cfg: Config, _args: argparse.Namespace) -> int:
    from netwatch.daemon import Daemon
    daemon = Daemon(cfg)
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        daemon.stop()
    return 0


def _cmd_tui(cfg: Config, _args: argparse.Namespace) -> int:  # pragma: no cover
    from netwatch.daemon import Daemon
    from netwatch.tui import NetwatchApp

    daemon = Daemon(cfg)

    async def _run() -> None:
        daemon_task = asyncio.create_task(daemon.run())
        try:
            await NetwatchApp(daemon).run_async()
        finally:
            daemon.stop()
            await daemon_task

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    return 0


def _cmd_unlock(cfg: Config, _args: argparse.Namespace) -> int:
    """Out-of-process unlock: just verifies the password matches.

    Inter-process unlock would require an IPC socket; for v0.1.0 the TUI
    'u' key is the authoritative path. This subcommand exists for scripted
    health-checks and to let an operator confirm their password works
    without triggering a lockdown.
    """
    pw = getpass.getpass("Unlock password: ")
    if auth.verify_at(cfg.auth_path, pw):
        print("password OK"); return 0
    print("password rejected", file=sys.stderr); return 1


def _cmd_status(cfg: Config, _args: argparse.Namespace) -> int:
    baseline = Baseline.load(cfg.baseline.path, learning_seconds=cfg.baseline.learning_seconds)
    print(json.dumps({
        "baseline_size": len(baseline.devices),
        "whitelist_size": len(baseline.whitelist),
        "baseline_path": str(cfg.baseline.path),
        "auth_path": str(cfg.auth_path),
        "version": __version__,
    }, indent=2))
    return 0


_DISPATCH = {
    "version": _cmd_version,
    "setpassword": _cmd_setpassword,
    "whitelist": _cmd_whitelist,
    "baseline": _cmd_baseline,
    "daemon": _cmd_daemon,
    "tui": _cmd_tui,
    "unlock": _cmd_unlock,
    "status": _cmd_status,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.config)
    except (ValueError, OSError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    handler = _DISPATCH.get(args.command)
    if handler is None:
        parser.error(f"unknown command {args.command}")
    return handler(cfg, args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


# Quiet the unused-import lint when running on platforms without certain deps.
_ = os
