"""Tests for the IPC socket permission policy.

v0.3.0: the IPC socket fails CLOSED when the `usbdefense` group is
missing, instead of falling back to mode 0666 with a warning. The
escape hatch is `USB_DEFENSE_IPC_ALLOW_OPEN=1` (logs a loud warning).

These tests exercise `_apply_socket_permissions` in isolation by
constructing an IPCServer without ever opening a real socket — we just
need an object that owns a `socket_path` attribute.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from usbguard_defense import ipc


def _make_server(tmp_path) -> ipc.IPCServer:
    server = ipc.IPCServer(socket_path=tmp_path / "ipc.sock")
    (tmp_path / "ipc.sock").write_text("")
    return server


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only behavior")
def test_apply_perms_fails_closed_when_group_missing(tmp_path, monkeypatch):
    server = _make_server(tmp_path)
    monkeypatch.delenv("USB_DEFENSE_IPC_ALLOW_OPEN", raising=False)
    fake_grp = SimpleNamespace(getgrnam=lambda _: (_ for _ in ()).throw(KeyError("usbdefense")))
    monkeypatch.setattr(ipc, "grp", fake_grp)
    with pytest.raises(RuntimeError, match="usbdefense"):
        server._apply_socket_permissions()


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only behavior")
def test_apply_perms_open_override_chmods_world_writable(tmp_path, monkeypatch):
    server = _make_server(tmp_path)
    monkeypatch.setenv("USB_DEFENSE_IPC_ALLOW_OPEN", "1")
    # Even if grp would have worked, the env var short-circuits.
    fake_grp = SimpleNamespace(getgrnam=lambda _: SimpleNamespace(gr_gid=42))
    monkeypatch.setattr(ipc, "grp", fake_grp)
    chmod_calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        ipc.os, "chmod",
        lambda path, mode: chmod_calls.append((str(path), mode)),
    )
    server._apply_socket_permissions()  # must not raise
    assert chmod_calls and chmod_calls[-1][1] == 0o666


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only behavior")
def test_apply_perms_locks_socket_when_group_present(tmp_path, monkeypatch):
    server = _make_server(tmp_path)
    monkeypatch.delenv("USB_DEFENSE_IPC_ALLOW_OPEN", raising=False)
    fake_grp = SimpleNamespace(getgrnam=lambda _: SimpleNamespace(gr_gid=4242))
    monkeypatch.setattr(ipc, "grp", fake_grp)
    chown_calls: list[tuple[str, int, int]] = []
    chmod_calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        ipc.os, "chown",
        lambda path, uid, gid: chown_calls.append((str(path), uid, gid)),
    )
    monkeypatch.setattr(
        ipc.os, "chmod",
        lambda path, mode: chmod_calls.append((str(path), mode)),
    )
    server._apply_socket_permissions()
    assert chown_calls == [(str(server.socket_path), 0, 4242)]
    assert chmod_calls == [(str(server.socket_path), 0o660)]


def test_apply_perms_skips_silently_on_non_posix(tmp_path, monkeypatch):
    """On Windows there is no socket-perms concept; the method must no-op."""
    server = _make_server(tmp_path)
    monkeypatch.setattr(ipc.os, "name", "nt")
    # Should not raise even though grp is None / unavailable.
    server._apply_socket_permissions()
