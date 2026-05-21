"""Daemon ↔ UI inter-process communication via Unix socket + JSON lines."""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
from pathlib import Path
from typing import Callable, Optional

from .config import IPC_SOCKET


log = logging.getLogger(__name__)


class IPCServer:
    """Daemon side. Accepts UI clients, broadcasts events to all of them."""

    def __init__(self, socket_path: Path = IPC_SOCKET):
        self.socket_path = socket_path
        self._sock: Optional[socket.socket] = None
        self._clients: list[socket.socket] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.on_command: Optional[Callable[[dict], dict]] = None

    def start(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            self.socket_path.unlink()
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(self.socket_path))
        self._sock.listen(8)
        os.chmod(self.socket_path, 0o666)  # any local user can connect; for production, use a dedicated usbdefense group + 0660
        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="IPCServer")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            for c in self._clients:
                try: c.close()
                except Exception: pass
            self._clients.clear()
        if self._sock:
            try: self._sock.close()
            except Exception: pass
        if self.socket_path.exists():
            try: self.socket_path.unlink()
            except Exception: pass

    def broadcast(self, event: dict) -> None:
        line = (json.dumps(event) + "\n").encode("utf-8")
        with self._lock:
            dead: list[socket.socket] = []
            for c in self._clients:
                try:
                    c.sendall(line)
                except OSError:
                    dead.append(c)
            for d in dead:
                self._clients.remove(d)
                try: d.close()
                except Exception: pass

    def _accept_loop(self) -> None:
        assert self._sock is not None
        self._sock.settimeout(1.0)
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                self._clients.append(conn)
            threading.Thread(
                target=self._client_loop, args=(conn,), daemon=True,
                name="IPCClient",
            ).start()

    def _client_loop(self, conn: socket.socket) -> None:
        buf = b""
        try:
            while not self._stop.is_set():
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    if self.on_command:
                        try:
                            response = self.on_command(msg) or {}
                        except Exception as exc:
                            log.exception("Command handler raised")
                            response = {"error": str(exc)}
                        try:
                            conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
                        except OSError:
                            break
        finally:
            with self._lock:
                if conn in self._clients:
                    self._clients.remove(conn)
            try: conn.close()
            except Exception: pass


class IPCClient:
    """UI side. Connects to daemon, sends commands, receives events."""

    def __init__(self, socket_path: Path = IPC_SOCKET):
        self.socket_path = socket_path
        self._sock: Optional[socket.socket] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.on_event: Optional[Callable[[dict], None]] = None

    def connect(self) -> bool:
        try:
            self._stop.clear()
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.connect(str(self.socket_path))
            self._thread = threading.Thread(target=self._recv_loop, daemon=True, name="IPCRecv")
            self._thread.start()
            return True
        except OSError as exc:
            log.error("Cannot connect to daemon: %s", exc)
            self._sock = None
            return False

    def is_connected(self) -> bool:
        return self._sock is not None

    def disconnect(self) -> None:
        self._stop.set()
        if self._sock:
            try: self._sock.close()
            except Exception: pass
        self._sock = None

    def send_command(self, msg: dict) -> None:
        if not self._sock:
            return
        try:
            self._sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))
        except OSError:
            log.warning("send_command failed — marking socket dead")
            try: self._sock.close()
            except Exception: pass
            self._sock = None

    def _recv_loop(self) -> None:
        assert self._sock is not None
        buf = b""
        try:
            while not self._stop.is_set():
                try:
                    chunk = self._sock.recv(4096)
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    if self.on_event:
                        try:
                            self.on_event(event)
                        except Exception:
                            log.exception("on_event handler raised")
        finally:
            # Mark socket dead so the UI can re-connect on its refresh tick.
            sock = self._sock
            self._sock = None
            if sock is not None:
                try: sock.close()
                except Exception: pass
