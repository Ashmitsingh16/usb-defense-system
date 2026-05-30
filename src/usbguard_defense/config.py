"""Configuration loading and constants."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


CONFIG_PATH = Path(os.environ.get("USB_DEFENSE_CONFIG", "/etc/usb-defense/config.yaml"))
WHITELIST_PATH = Path("/etc/usb-defense/whitelist.json")
WHITELIST_SIG_PATH = Path("/etc/usb-defense/whitelist.sig")
ADMIN_HASH_PATH = Path("/etc/usb-defense/admin.hash")
RECOVERY_SEED_HASH_PATH = Path("/etc/usb-defense/recovery_seed.hash")
MASTER_KEY_PATH = Path("/etc/usb-defense/master.key")
EVENT_LOG_PATH = Path("/var/log/usb-defense/events.log")
RUNTIME_DIR = Path("/run/usb-defense")
IPC_SOCKET = RUNTIME_DIR / "ipc.sock"
LOCKDOWN_FLAG = RUNTIME_DIR / "lockdown.flag"
PID_FILE = RUNTIME_DIR / "daemon.pid"
PERSISTENT_LOCKDOWN_FLAG = Path("/var/lib/usb-defense/lockdown.flag")
ASSETS_DIR = Path("/usr/lib/usb-defense/assets")


@dataclass
class Config:
    alarm_enabled: bool = True
    alarm_volume: int = 80  # 0-100
    alarm_sound: str = "alarm.wav"  # filename in ASSETS_DIR
    lockdown_grace_period_sec: int = 0  # 0 = immediate
    lockdown_screen_lock: bool = True
    require_unlock_key: bool = True  # only USBs flagged can_unlock=True can clear lockdown
    daemon_log_level: str = "INFO"
    notify_on_authorized: bool = True
    auto_block_unknown: bool = True
    audit_journald: bool = True
    audit_flat_file: bool = True
    # Simulator: allows tests/simulate.py to drive lockdown enter/clear via
    # IPC without real USB hardware. Even when enabled the daemon now
    # password-gates every simulate_event call. Default off; flip on only
    # for the viva demos.
    simulator_enabled: bool = False


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Load YAML config; fall back to defaults if file missing."""
    if not path.exists():
        return Config()
    with path.open("r") as fh:
        data = yaml.safe_load(fh) or {}
    cfg = Config()
    for key, value in data.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    return cfg
