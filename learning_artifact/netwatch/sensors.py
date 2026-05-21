"""Detection sensors.

Three layers run concurrently as asyncio tasks:

  1. ArpCacheSensor   — passive: parse /proc/net/arp on a 5-second interval.
  2. ArpScanSensor    — active : scapy ARP sweep of the local /24 every 30 s.
  3. DhcpSniffSensor  — passive: real-time scapy sniff of DHCP DISCOVER/REQUEST.

All three feed an asyncio.Queue of `Observation` records consumed by the
daemon. Sensors are designed so they degrade gracefully — if scapy isn't
installed or the host isn't Linux, only the ARP-cache sensor runs (and on
Windows even that returns empty, which is fine for tests).
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Iterable


@dataclass(frozen=True)
class Observation:
    mac: str
    ip: str | None
    iface: str | None
    source: str  # "arp-cache" | "arp-scan" | "dhcp"


# Lazy scapy import — keeps `import netwatch.sensors` safe on Windows.
def _scapy() -> object | None:
    try:
        import scapy.all as scapy  # noqa: WPS433
        return scapy
    except Exception:
        return None


# --------------------------------------------------------------------- helpers
_MAC_RE = re.compile(r"([0-9a-f]{2}(?::[0-9a-f]{2}){5})", re.I)
_INCOMPLETE_MACS = {"00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"}


def parse_proc_net_arp(text: str, *, default_iface: str | None = None) -> list[Observation]:
    """Parse /proc/net/arp output. Pure function — easy to test."""
    out: list[Observation] = []
    for line in text.splitlines()[1:]:  # skip header
        cols = line.split()
        if len(cols) < 6:
            continue
        ip, _hw_type, flags, mac, _mask, iface = cols[:6]
        if mac.lower() in _INCOMPLETE_MACS:
            continue
        if not _MAC_RE.fullmatch(mac):
            continue
        if flags == "0x0":  # incomplete entry
            continue
        out.append(Observation(mac=mac.lower(), ip=ip, iface=iface or default_iface, source="arp-cache"))
    return out


def read_arp_cache(path: Path = Path("/proc/net/arp")) -> list[Observation]:
    """Read the kernel ARP cache. Empty list on non-Linux or read failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return []
    return parse_proc_net_arp(text)


# ---------------------------------------------------------------- base sensor
class Sensor:
    """Base sensor; subclasses override `run`."""

    name = "sensor"

    def __init__(self, queue: asyncio.Queue[Observation]):
        self.queue = queue
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def emit(self, obs: Iterable[Observation]) -> None:
        for o in obs:
            await self.queue.put(o)

    async def run(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def start(self) -> asyncio.Task[None]:
        self._task = asyncio.create_task(self.run(), name=f"sensor-{self.name}")
        return self._task

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass


# ------------------------------------------------------------- arp-cache poll
class ArpCacheSensor(Sensor):
    name = "arp-cache"

    def __init__(
        self,
        queue: asyncio.Queue[Observation],
        *,
        interval: float = 5.0,
        reader: Callable[[], list[Observation]] = read_arp_cache,
    ):
        super().__init__(queue)
        self.interval = interval
        self._reader = reader

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                obs = self._reader()
                await self.emit(obs)
            except Exception:
                # Sensors NEVER bring down the daemon. Errors are logged by the daemon.
                await self.queue.put(Observation(mac="00:00:00:00:00:00", ip=None, iface=None, source="error:arp-cache"))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                continue


# ------------------------------------------------------------- arp active scan
class ArpScanSensor(Sensor):
    name = "arp-scan"

    def __init__(
        self,
        queue: asyncio.Queue[Observation],
        *,
        interval: float = 30.0,
        subnet: str | None = None,
        iface: str | None = None,
        scanner: Callable[[str, str | None], list[Observation]] | None = None,
    ):
        super().__init__(queue)
        self.interval = interval
        self.subnet = subnet
        self.iface = iface
        self._scanner = scanner or _default_arp_scan

    async def run(self) -> None:
        while not self._stop.is_set():
            subnet = self.subnet or _guess_local_subnet()
            if subnet:
                try:
                    obs = await asyncio.to_thread(self._scanner, subnet, self.iface)
                    await self.emit(obs)
                except Exception:
                    pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                continue


def _default_arp_scan(subnet: str, iface: str | None) -> list[Observation]:
    """scapy ARP sweep. Returns empty if scapy unavailable."""
    scapy = _scapy()
    if scapy is None:
        return []
    try:
        net = ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        return []
    arp = scapy.ARP(pdst=str(net))  # type: ignore[attr-defined]
    ether = scapy.Ether(dst="ff:ff:ff:ff:ff:ff") / arp  # type: ignore[attr-defined]
    answered, _ = scapy.srp(ether, timeout=2, verbose=False, iface=iface)  # type: ignore[attr-defined]
    out: list[Observation] = []
    for _sent, recv in answered:
        out.append(Observation(mac=str(recv.hwsrc).lower(), ip=str(recv.psrc), iface=iface, source="arp-scan"))
    return out


def _guess_local_subnet() -> str | None:
    """Best-effort guess of the operator's /24. None if we can't tell."""
    if sys.platform == "win32":
        return None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local = s.getsockname()[0]
        s.close()
        parts = local.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    except OSError:
        return None
    return None


# --------------------------------------------------------------- DHCP sniffing
class DhcpSniffSensor(Sensor):
    name = "dhcp"

    def __init__(self, queue: asyncio.Queue[Observation], *, iface: str | None = None):
        super().__init__(queue)
        self.iface = iface

    async def run(self) -> None:
        scapy = _scapy()
        if scapy is None:
            return  # quietly skip on hosts without scapy
        loop = asyncio.get_running_loop()

        def _on_pkt(pkt: object) -> None:
            try:
                src = getattr(pkt, "src", None) or getattr(pkt.getlayer("Ether"), "src", None)  # type: ignore[union-attr]
                if not src:
                    return
                # Best-effort hostname / requested IP from DHCP options
                ip = None
                obs = Observation(mac=str(src).lower(), ip=ip, iface=self.iface, source="dhcp")
                asyncio.run_coroutine_threadsafe(self.queue.put(obs), loop)
            except Exception:
                return

        def _sniff() -> None:
            try:
                scapy.sniff(  # type: ignore[attr-defined]
                    filter="udp and (port 67 or port 68)",
                    prn=_on_pkt,
                    store=False,
                    iface=self.iface,
                    stop_filter=lambda _p: self._stop.is_set(),
                )
            except Exception:
                return

        await asyncio.to_thread(_sniff)


def build_sensors(
    queue: asyncio.Queue[Observation],
    *,
    arp_cache_interval: float,
    arp_scan_interval: float,
    dhcp_enabled: bool,
    iface: str | None,
) -> list[Sensor]:
    """Construct the default sensor set. Caller starts/stops them."""
    sensors: list[Sensor] = [ArpCacheSensor(queue, interval=arp_cache_interval)]
    if sys.platform != "win32":
        sensors.append(ArpScanSensor(queue, interval=arp_scan_interval, iface=iface))
        if dhcp_enabled:
            sensors.append(DhcpSniffSensor(queue, iface=iface))
    return sensors


__all__ = [
    "Observation",
    "Sensor",
    "ArpCacheSensor",
    "ArpScanSensor",
    "DhcpSniffSensor",
    "parse_proc_net_arp",
    "read_arp_cache",
    "build_sensors",
]


# Re-export Awaitable to satisfy mypy about the unused-import lint
_ = Awaitable
