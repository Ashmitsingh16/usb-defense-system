"""Pydantic-validated configuration loaded from YAML.

The whole daemon must be configurable from one file; defaults are sane so an
operator can run `netwatch daemon` on a clean install without writing YAML.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


DEFAULT_CONFIG_PATH = Path("/etc/netwatch/netwatch.yaml")
DEFAULT_AUTH_PATH = Path("/etc/netwatch/auth.json")
DEFAULT_BASELINE_PATH = Path("/var/lib/netwatch/baseline.json")
DEFAULT_LOG_DIR = Path("/var/log/netwatch")
DEFAULT_SOCKET = Path("/run/netwatch/netwatch.sock")


class SensorConfig(BaseModel):
    """Per-sensor tuning. All intervals in seconds."""

    arp_cache_interval: float = Field(default=5.0, gt=0)
    arp_scan_interval: float = Field(default=30.0, gt=0)
    dhcp_sniff_enabled: bool = True
    interface: str | None = None  # auto-detect when None

    @field_validator("interface")
    @classmethod
    def _normalize_interface(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ResponderConfig(BaseModel):
    """How the daemon responds to a detected intruder."""

    freeze_network: bool = True
    use_nftables: bool = True  # falls back to `ip link` if nft unavailable
    preserve_ssh: bool = True
    fallback_iface_down: bool = True


class BaselineConfig(BaseModel):
    learning_seconds: int = Field(default=90, ge=0)
    path: Path = DEFAULT_BASELINE_PATH


class LoggingConfig(BaseModel):
    dir: Path = DEFAULT_LOG_DIR
    max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    backup_count: int = Field(default=5, ge=0)
    journald: bool = True


class Config(BaseModel):
    """Top-level config object."""

    sensors: SensorConfig = Field(default_factory=SensorConfig)
    responder: ResponderConfig = Field(default_factory=ResponderConfig)
    baseline: BaselineConfig = Field(default_factory=BaselineConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    auth_path: Path = DEFAULT_AUTH_PATH
    socket_path: Path = DEFAULT_SOCKET
    whitelist: list[str] = Field(default_factory=list)

    @field_validator("whitelist")
    @classmethod
    def _normalize_macs(cls, v: list[str]) -> list[str]:
        return sorted({mac.strip().lower() for mac in v if mac.strip()})


def load_config(path: Path | str | None = None) -> Config:
    """Load and validate config from YAML.

    A missing file is not an error — we use full defaults. This makes
    `netwatch daemon` trivially demoable on a fresh box.
    """
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if not p.exists():
        return Config()
    raw: Any = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config root must be a mapping, got {type(raw).__name__}")
    return Config.model_validate(raw)


def dump_default_yaml() -> str:
    """Render the default config as YAML — used by `scripts/install.sh`."""
    cfg = Config()
    return yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False)
