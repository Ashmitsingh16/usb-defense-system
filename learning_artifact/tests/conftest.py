from __future__ import annotations

import logging
from pathlib import Path

import pytest

from netwatch.config import (
    BaselineConfig, Config, LoggingConfig, ResponderConfig, SensorConfig,
)


@pytest.fixture
def tmp_cfg(tmp_path: Path) -> Config:
    return Config(
        sensors=SensorConfig(arp_cache_interval=0.1, arp_scan_interval=0.1, dhcp_sniff_enabled=False),
        responder=ResponderConfig(),
        baseline=BaselineConfig(learning_seconds=0, path=tmp_path / "baseline.json"),
        logging=LoggingConfig(dir=tmp_path / "logs", max_bytes=1_000_000, backup_count=1, journald=False),
        auth_path=tmp_path / "auth.json",
        socket_path=tmp_path / "netwatch.sock",
    )


@pytest.fixture
def null_logger() -> logging.Logger:
    logger = logging.getLogger("netwatch-test")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger
