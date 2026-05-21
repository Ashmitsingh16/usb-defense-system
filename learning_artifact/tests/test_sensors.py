from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from netwatch.sensors import (
    ArpCacheSensor,
    Observation,
    parse_proc_net_arp,
    read_arp_cache,
)


SAMPLE_ARP = """IP address       HW type     Flags       HW address            Mask     Device
192.168.1.1      0x1         0x2         aa:bb:cc:dd:ee:01     *        eth0
192.168.1.2      0x1         0x0         00:00:00:00:00:00     *        eth0
192.168.1.3      0x1         0x2         AA:BB:CC:DD:EE:02     *        wlan0
malformed line
192.168.1.4      0x1         0x2         not-a-mac             *        eth0
"""


def test_parse_proc_net_arp() -> None:
    obs = parse_proc_net_arp(SAMPLE_ARP)
    macs = {o.mac for o in obs}
    assert macs == {"aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"}
    by_mac = {o.mac: o for o in obs}
    assert by_mac["aa:bb:cc:dd:ee:01"].iface == "eth0"
    assert by_mac["aa:bb:cc:dd:ee:01"].source == "arp-cache"


def test_read_arp_cache_missing(tmp_path: Path) -> None:
    # On Windows /proc/net/arp doesn't exist; this exercises the same branch.
    assert read_arp_cache(tmp_path / "missing") == []


@pytest.mark.asyncio
async def test_arp_cache_sensor_emits() -> None:
    queue: asyncio.Queue[Observation] = asyncio.Queue()
    fake = [
        Observation(mac="aa:bb:cc:dd:ee:01", ip="10.0.0.1", iface="eth0", source="arp-cache"),
    ]
    sensor = ArpCacheSensor(queue, interval=0.05, reader=lambda: fake)
    sensor.start()
    obs = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert obs.mac == "aa:bb:cc:dd:ee:01"
    await sensor.stop()


@pytest.mark.asyncio
async def test_arp_scan_sensor_uses_injected_scanner() -> None:
    from netwatch.sensors import ArpScanSensor
    queue: asyncio.Queue[Observation] = asyncio.Queue()

    def scanner(subnet: str, iface: str | None) -> list[Observation]:
        return [Observation("aa:bb:cc:dd:ee:11", "10.0.0.5", iface, "arp-scan")]

    sensor = ArpScanSensor(queue, interval=0.05, subnet="10.0.0.0/30", iface="eth0", scanner=scanner)
    sensor.start()
    obs = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert obs.source == "arp-scan"
    assert obs.mac == "aa:bb:cc:dd:ee:11"
    await sensor.stop()


@pytest.mark.asyncio
async def test_arp_scan_sensor_handles_scanner_error() -> None:
    from netwatch.sensors import ArpScanSensor
    queue: asyncio.Queue[Observation] = asyncio.Queue()

    def boom(_subnet: str, _iface: str | None) -> list[Observation]:
        raise RuntimeError("ifdown")

    sensor = ArpScanSensor(queue, interval=0.05, subnet="10.0.0.0/30", scanner=boom)
    sensor.start()
    # The sensor swallows scanner errors silently; verify by stopping cleanly.
    await asyncio.sleep(0.15)
    await sensor.stop()
    assert queue.empty()


def test_default_arp_scan_handles_bad_subnet() -> None:
    from netwatch.sensors import _default_arp_scan
    assert _default_arp_scan("not-a-cidr", None) == []


def test_default_arp_scan_no_scapy(monkeypatch: pytest.MonkeyPatch) -> None:
    import netwatch.sensors as sensors_mod
    monkeypatch.setattr(sensors_mod, "_scapy", lambda: None)
    assert sensors_mod._default_arp_scan("10.0.0.0/30", None) == []


def test_build_sensors_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    import netwatch.sensors as sensors_mod
    monkeypatch.setattr(sensors_mod.sys, "platform", "win32")
    sensors = sensors_mod.build_sensors(
        asyncio.Queue(), arp_cache_interval=1, arp_scan_interval=1, dhcp_enabled=True, iface=None,
    )
    assert len(sensors) == 1
    assert sensors[0].name == "arp-cache"


def test_build_sensors_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    import netwatch.sensors as sensors_mod
    monkeypatch.setattr(sensors_mod.sys, "platform", "linux")
    sensors = sensors_mod.build_sensors(
        asyncio.Queue(), arp_cache_interval=1, arp_scan_interval=1, dhcp_enabled=True, iface=None,
    )
    names = {s.name for s in sensors}
    assert {"arp-cache", "arp-scan", "dhcp"} <= names


def test_guess_local_subnet_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    import netwatch.sensors as sensors_mod
    monkeypatch.setattr(sensors_mod.sys, "platform", "win32")
    assert sensors_mod._guess_local_subnet() is None


@pytest.mark.asyncio
async def test_dhcp_sniff_returns_when_no_scapy(monkeypatch: pytest.MonkeyPatch) -> None:
    from netwatch.sensors import DhcpSniffSensor
    import netwatch.sensors as sensors_mod
    monkeypatch.setattr(sensors_mod, "_scapy", lambda: None)
    queue: asyncio.Queue[Observation] = asyncio.Queue()
    sensor = DhcpSniffSensor(queue)
    task = sensor.start()
    await asyncio.wait_for(task, timeout=1.0)  # exits immediately


@pytest.mark.asyncio
async def test_arp_cache_sensor_handles_reader_error() -> None:
    queue: asyncio.Queue[Observation] = asyncio.Queue()

    def boom() -> list[Observation]:
        raise RuntimeError("disk gone")

    sensor = ArpCacheSensor(queue, interval=0.05, reader=boom)
    sensor.start()
    obs = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert obs.source.startswith("error:")
    await sensor.stop()
