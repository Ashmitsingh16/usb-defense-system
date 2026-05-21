from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from netwatch import cli


def _run(argv: list[str], tmp_path: Path) -> int:
    cfg_path = tmp_path / "netwatch.yaml"
    cfg_path.write_text(
        f"baseline:\n  path: {tmp_path / 'bl.json'}\n  learning_seconds: 0\n"
        f"auth_path: {tmp_path / 'auth.json'}\n"
        f"logging:\n  dir: {tmp_path / 'logs'}\n"
    )
    return cli.main(["--config", str(cfg_path), *argv])


def test_version(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    rc = _run(["version"], tmp_path)
    assert rc == 0
    assert "netwatch" in capsys.readouterr().out


def test_setpassword_from_stdin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("secret\n"))
    rc = _run(["setpassword", "--from-stdin"], tmp_path)
    assert rc == 0
    assert (tmp_path / "auth.json").exists()


def test_setpassword_empty_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    rc = _run(["setpassword", "--from-stdin"], tmp_path)
    assert rc == 2


def test_whitelist_add_list_remove(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert _run(["whitelist", "add", "AA:BB:CC:DD:EE:01"], tmp_path) == 0
    assert _run(["whitelist", "list"], tmp_path) == 0
    out = capsys.readouterr().out
    assert "aa:bb:cc:dd:ee:01" in out
    assert _run(["whitelist", "remove", "aa:bb:cc:dd:ee:01"], tmp_path) == 0
    assert _run(["whitelist", "remove", "aa:bb:cc:dd:ee:01"], tmp_path) == 1


def test_whitelist_invalid(tmp_path: Path) -> None:
    assert _run(["whitelist", "add", "garbage"], tmp_path) == 2


def test_baseline_show_and_rebuild(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert _run(["baseline", "rebuild"], tmp_path) == 0
    capsys.readouterr()  # discard rebuild output
    assert _run(["baseline", "show"], tmp_path) == 0
    out = capsys.readouterr().out
    json.loads(out)  # must parse


def test_status(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert _run(["status"], tmp_path) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert "baseline_size" in parsed


def test_unlock_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("pw\n"))
    _run(["setpassword", "--from-stdin"], tmp_path)
    monkeypatch.setattr("getpass.getpass", lambda *_a, **_k: "pw")
    assert _run(["unlock"], tmp_path) == 0


def test_unlock_fail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("pw\n"))
    _run(["setpassword", "--from-stdin"], tmp_path)
    monkeypatch.setattr("getpass.getpass", lambda *_a, **_k: "wrong")
    assert _run(["unlock"], tmp_path) == 1


def test_bad_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("- 1\n")
    rc = cli.main(["--config", str(bad), "version"])
    assert rc == 2
