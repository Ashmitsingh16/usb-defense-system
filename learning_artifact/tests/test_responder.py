from __future__ import annotations

from typing import Sequence

from netwatch.responder import CommandResult, Responder


class FakeRunner:
    def __init__(self, *, ok: bool = True) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.ok = ok

    def __call__(self, args: Sequence[str]) -> CommandResult:
        self.calls.append(tuple(args))
        return CommandResult(args=tuple(args), returncode=0 if self.ok else 1)


def test_freeze_with_nft_no_ssh() -> None:
    runner = FakeRunner()
    r = Responder(runner=runner, env={}, nft_available=lambda: True)
    out = r.freeze()
    assert out.method == "nftables"
    assert out.success
    assert r.frozen
    # Must contain accept-on-lo and ct established rules.
    flat = [" ".join(c) for c in runner.calls]
    assert any("iif lo accept" in c for c in flat)
    assert any("established,related" in c for c in flat)


def test_freeze_preserves_ssh() -> None:
    runner = FakeRunner()
    env = {"SSH_CONNECTION": "203.0.113.5 51322 192.0.2.1 22"}
    r = Responder(runner=runner, env=env, nft_available=lambda: True)
    out = r.freeze()
    assert out.preserved_ssh == "203.0.113.5:22"
    flat = [" ".join(c) for c in runner.calls]
    assert any("203.0.113.5" in c and "22" in c for c in flat)


def test_freeze_falls_back_to_iplink_when_nft_missing() -> None:
    runner = FakeRunner()
    r = Responder(runner=runner, env={}, nft_available=lambda: False)
    out = r.freeze(fallback_iface="eth0")
    assert out.method == "iplink"
    assert runner.calls[-1] == ("ip", "link", "set", "eth0", "down")


def test_freeze_idempotent() -> None:
    runner = FakeRunner()
    r = Responder(runner=runner, env={}, nft_available=lambda: True)
    r.freeze()
    n = len(runner.calls)
    r.freeze()
    assert len(runner.calls) == n  # second call is a no-op


def test_unfreeze_after_nft() -> None:
    runner = FakeRunner()
    r = Responder(runner=runner, env={}, nft_available=lambda: True)
    r.freeze()
    runner.calls.clear()
    r.unfreeze()
    assert any("delete" in " ".join(c) for c in runner.calls)
    assert not r.frozen


def test_unfreeze_after_iplink_brings_up() -> None:
    runner = FakeRunner()
    r = Responder(runner=runner, env={}, nft_available=lambda: False)
    r.freeze(fallback_iface="eth0")
    runner.calls.clear()
    r.unfreeze()
    assert ("ip", "link", "set", "eth0", "up") in runner.calls


def test_no_method_when_nft_missing_and_no_fallback() -> None:
    runner = FakeRunner()
    r = Responder(runner=runner, env={}, nft_available=lambda: False)
    out = r.freeze()
    assert out.method == "none"
    assert not out.success


def test_malformed_ssh_connection_ignored() -> None:
    runner = FakeRunner()
    r = Responder(runner=runner, env={"SSH_CONNECTION": "garbage"}, nft_available=lambda: True)
    out = r.freeze()
    assert out.preserved_ssh is None
