from __future__ import annotations

import logging
import time
from typing import Sequence

import pytest

from netwatch.config import Config
from netwatch.daemon import Daemon
from netwatch.events import EventType
from netwatch.responder import CommandResult, Responder
from netwatch.sensors import Observation
from netwatch import auth


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, args: Sequence[str]) -> CommandResult:
        self.calls.append(tuple(args))
        return CommandResult(args=tuple(args), returncode=0)


def _make_daemon(cfg: Config) -> tuple[Daemon, _FakeRunner]:
    runner = _FakeRunner()
    responder = Responder(runner=runner, env={}, nft_available=lambda: True)
    d = Daemon(cfg, responder=responder, logger=logging.getLogger("netwatch-test"))
    return d, runner


def test_known_device_no_alert(tmp_cfg: Config) -> None:
    d, _ = _make_daemon(tmp_cfg)
    # learning_seconds=0, so first observe = intruder. Whitelist it first.
    d.add_whitelist("aa:bb:cc:dd:ee:01")
    alert = d.handle_observation(Observation("aa:bb:cc:dd:ee:01", "10.0.0.1", "eth0", "arp-cache"))
    assert alert is None
    assert not d.state.locked


def test_intruder_triggers_freeze_and_lock(tmp_cfg: Config) -> None:
    d, runner = _make_daemon(tmp_cfg)
    alert = d.handle_observation(Observation("de:ad:be:ef:00:01", "10.0.0.42", "eth0", "arp-scan"))
    assert alert is not None
    assert d.state.locked
    assert d.state.frozen
    assert runner.calls  # nft commands ran
    # Lock reason matches alert
    assert d.state.lock_reason is not None
    assert d.state.lock_reason.mac == "de:ad:be:ef:00:01"


def test_duplicate_alerts_debounced(tmp_cfg: Config) -> None:
    d, _ = _make_daemon(tmp_cfg)
    obs = Observation("de:ad:be:ef:00:02", "10.0.0.43", "eth0", "arp-scan")
    a1 = d.handle_observation(obs)
    a2 = d.handle_observation(obs)
    assert a1 is not None
    assert a2 is None  # debounced
    assert len(d.state.alerts) == 1


def test_unlock_requires_password(tmp_cfg: Config) -> None:
    auth.write_auth(tmp_cfg.auth_path, "letmein")
    d, _ = _make_daemon(tmp_cfg)
    d.handle_observation(Observation("de:ad:be:ef:00:03", None, None, "arp-scan"))
    assert d.state.locked

    bad = d.unlock("nope")
    assert not bad.ok
    assert d.state.locked
    assert d.state.failed_unlocks == 1

    good = d.unlock("letmein")
    assert good.ok
    assert not d.state.locked
    assert not d.state.frozen


def test_unlock_when_not_locked(tmp_cfg: Config) -> None:
    d, _ = _make_daemon(tmp_cfg)
    res = d.unlock("anything")
    assert not res.ok
    assert "not locked" in res.reason


def test_unlock_lockout_after_max_attempts(tmp_cfg: Config) -> None:
    auth.write_auth(tmp_cfg.auth_path, "real")
    d, _ = _make_daemon(tmp_cfg)
    d.handle_observation(Observation("de:ad:be:ef:00:04", None, None, "arp-scan"))
    for _ in range(Daemon.MAX_FAILED_UNLOCKS):
        d.unlock("wrong")
    res = d.unlock("real")
    assert not res.ok
    assert "too many" in res.reason


def test_force_freeze_manual(tmp_cfg: Config) -> None:
    d, runner = _make_daemon(tmp_cfg)
    d.force_freeze()
    assert d.state.locked
    assert runner.calls


def test_whitelist_add_remove(tmp_cfg: Config) -> None:
    d, _ = _make_daemon(tmp_cfg)
    assert d.add_whitelist("aa:bb:cc:dd:ee:09") is True
    assert d.add_whitelist("garbage") is False
    assert d.remove_whitelist("aa:bb:cc:dd:ee:09") is True
    assert d.remove_whitelist("aa:bb:cc:dd:ee:09") is False


def test_rebuild_baseline_emits_event(tmp_cfg: Config) -> None:
    d, _ = _make_daemon(tmp_cfg)
    d.rebuild_baseline()
    types = [e.type for e in d.state.events]
    assert EventType.BASELINE_REBUILD in types


def test_sensor_error_observation_is_logged(tmp_cfg: Config) -> None:
    d, _ = _make_daemon(tmp_cfg)
    d.handle_observation(Observation("00:00:00:00:00:00", None, None, "error:arp-cache"))
    types = [e.type for e in d.state.events]
    assert EventType.SENSOR_ERROR in types


def test_malformed_mac_observation_dropped(tmp_cfg: Config) -> None:
    d, _ = _make_daemon(tmp_cfg)
    res = d.handle_observation(Observation("not-a-mac", None, None, "arp-scan"))
    assert res is None
    assert not d.state.locked


@pytest.mark.asyncio
async def test_daemon_run_and_stop(tmp_cfg: Config) -> None:
    import asyncio as _aio
    d, _ = _make_daemon(tmp_cfg)
    task = _aio.create_task(d.run())
    await _aio.sleep(0.2)
    d.stop()
    await _aio.wait_for(task, timeout=2.0)
    types = [e.type for e in d.state.events]
    assert EventType.DAEMON_START in types
    assert EventType.DAEMON_STOP in types


def test_lock_does_not_re_freeze(tmp_cfg: Config) -> None:
    d, runner = _make_daemon(tmp_cfg)
    d.handle_observation(Observation("de:ad:be:ef:00:05", None, None, "arp-scan"))
    n = len(runner.calls)
    # second intruder while locked -> trigger again, but state.locked already true
    # so _trigger_response short-circuits.
    d.handle_observation(Observation("de:ad:be:ef:00:06", None, None, "arp-scan"))
    assert len(runner.calls) == n
