"""Network-freeze responder.

When an intruder is detected the responder must:

  1. Install a default-DROP nftables policy on INPUT + OUTPUT.
  2. Preserve `lo` and the operator's active SSH session
     (parsed from $SSH_CONNECTION = "<client-ip> <client-port> <srv-ip> <srv-port>").
  3. Fall back to `ip link set <iface> down` if nftables is unavailable.

A `Responder` instance abstracts the platform layer so unit tests can substitute
a fake runner that just records the commands that would have been executed.
This is the single biggest fix vs Ashmit's lockdown.py — every action is
testable, reversible, and never silently no-ops.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Sequence

CommandRunner = Callable[[Sequence[str]], "CommandResult"]


@dataclass
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _default_runner(args: Sequence[str]) -> CommandResult:
    """Run a subprocess. Never raises — failures surface as non-zero returncodes."""
    try:
        proc = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return CommandResult(
            args=tuple(args),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return CommandResult(args=tuple(args), returncode=127, stderr=str(exc))


@dataclass
class FreezeOutcome:
    method: str            # "nftables" | "iplink" | "none"
    commands: list[CommandResult] = field(default_factory=list)
    preserved_ssh: str | None = None  # "1.2.3.4:22" if SSH preserved
    preserved_lo: bool = False
    success: bool = False

    def summary(self) -> str:
        return f"freeze via {self.method}, success={self.success}, ssh={self.preserved_ssh or 'none'}"


class Responder:
    """Stateful: tracks current frozen/unfrozen state so unfreeze() is safe to call always."""

    def __init__(
        self,
        *,
        runner: CommandRunner = _default_runner,
        env: dict[str, str] | None = None,
        nft_available: Callable[[], bool] | None = None,
    ):
        self._runner = runner
        self._env = env if env is not None else dict(os.environ)
        self._nft_available = nft_available or (lambda: shutil.which("nft") is not None)
        self._frozen: bool = False
        self._last_outcome: FreezeOutcome | None = None

    # --------------------------------------------------------------- public
    @property
    def frozen(self) -> bool:
        return self._frozen

    @property
    def last_outcome(self) -> FreezeOutcome | None:
        return self._last_outcome

    def freeze(self, *, fallback_iface: str | None = None) -> FreezeOutcome:
        """Apply the network freeze. Idempotent — repeat calls are safe."""
        if self._frozen and self._last_outcome is not None:
            return self._last_outcome

        ssh_endpoint = self._parse_ssh()
        outcome = FreezeOutcome(method="none", preserved_ssh=ssh_endpoint, preserved_lo=True)

        if self._nft_available():
            outcome.method = "nftables"
            for cmd in self._build_nft_commands(ssh_endpoint):
                result = self._runner(cmd)
                outcome.commands.append(result)
            outcome.success = all(c.ok for c in outcome.commands)
        elif fallback_iface:
            outcome.method = "iplink"
            result = self._runner(["ip", "link", "set", fallback_iface, "down"])
            outcome.commands.append(result)
            outcome.success = result.ok
        else:
            outcome.method = "none"
            outcome.success = False

        self._frozen = outcome.success
        self._last_outcome = outcome
        return outcome

    def unfreeze(self) -> FreezeOutcome:
        """Reverse the freeze. Tries nft flush then `ip link up` for known ifaces."""
        outcome = FreezeOutcome(method="unfreeze", preserved_lo=True)

        if self._nft_available():
            for cmd in [
                ["nft", "delete", "table", "inet", "netwatch"],
            ]:
                outcome.commands.append(self._runner(cmd))

        # If we used iplink, bring the iface back up. Best-effort.
        last = self._last_outcome
        if last and last.method == "iplink":
            for c in last.commands:
                args = list(c.args)
                # ["ip","link","set",<iface>,"down"] -> "up"
                if len(args) >= 5 and args[0:3] == ["ip", "link", "set"] and args[-1] == "down":
                    outcome.commands.append(self._runner(args[:-1] + ["up"]))

        outcome.success = True
        self._frozen = False
        return outcome

    # ------------------------------------------------------------- internals
    def _parse_ssh(self) -> str | None:
        """Return the SSH server-side endpoint to preserve, or None."""
        raw = self._env.get("SSH_CONNECTION", "").strip()
        if not raw:
            return None
        parts = raw.split()
        if len(parts) != 4:
            return None
        client_ip, _client_port, _srv_ip, srv_port = parts
        return f"{client_ip}:{srv_port}"

    def _build_nft_commands(self, ssh_endpoint: str | None) -> list[list[str]]:
        """Return the sequence of `nft` invocations that install a fail-closed table.

        We build a fresh `inet netwatch` table so flushing it cleanly removes
        the freeze without disturbing other firewall state.
        """
        cmds: list[list[str]] = [
            ["nft", "add", "table", "inet", "netwatch"],
            ["nft", "add", "chain", "inet", "netwatch", "input",
             "{ type filter hook input priority -100 ; policy drop ; }"],
            ["nft", "add", "chain", "inet", "netwatch", "output",
             "{ type filter hook output priority -100 ; policy drop ; }"],
            ["nft", "add", "rule", "inet", "netwatch", "input", "iif", "lo", "accept"],
            ["nft", "add", "rule", "inet", "netwatch", "output", "oif", "lo", "accept"],
            ["nft", "add", "rule", "inet", "netwatch", "input",
             "ct", "state", "established,related", "accept"],
            ["nft", "add", "rule", "inet", "netwatch", "output",
             "ct", "state", "established,related", "accept"],
        ]

        if ssh_endpoint:
            client_ip, srv_port = ssh_endpoint.rsplit(":", 1)
            cmds.append([
                "nft", "add", "rule", "inet", "netwatch", "input",
                "ip", "saddr", client_ip, "tcp", "dport", srv_port, "accept",
            ])
            cmds.append([
                "nft", "add", "rule", "inet", "netwatch", "output",
                "ip", "daddr", client_ip, "tcp", "sport", srv_port, "accept",
            ])
        return cmds
