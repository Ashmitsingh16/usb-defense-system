from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from netwatch.config import Config, dump_default_yaml, load_config


def test_load_default_when_missing(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "nope.yaml")
    assert isinstance(cfg, Config)
    assert cfg.sensors.arp_cache_interval > 0


def test_load_validates_yaml(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump({"sensors": {"arp_cache_interval": 1.5, "interface": "eth0"}}))
    cfg = load_config(p)
    assert cfg.sensors.arp_cache_interval == 1.5
    assert cfg.sensors.interface == "eth0"


def test_load_rejects_non_mapping(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text("- 1\n- 2\n")
    with pytest.raises(ValueError):
        load_config(p)


def test_whitelist_normalised(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump({"whitelist": [" AA:BB:CC:DD:EE:FF ", "aa:bb:cc:dd:ee:ff"]}))
    cfg = load_config(p)
    assert cfg.whitelist == ["aa:bb:cc:dd:ee:ff"]


def test_interface_empty_becomes_none(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump({"sensors": {"interface": "   "}}))
    cfg = load_config(p)
    assert cfg.sensors.interface is None


def test_dump_default_yaml_is_valid() -> None:
    blob = dump_default_yaml()
    parsed = yaml.safe_load(blob)
    assert "sensors" in parsed
    # round-trip through Config to prove validity
    Config.model_validate(parsed)


def test_negative_interval_rejected() -> None:
    with pytest.raises(Exception):
        Config.model_validate({"sensors": {"arp_cache_interval": -1}})
