"""Unit tests for config loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from usbguard_defense.config import Config, load_config


def test_defaults_when_file_missing(tmp_path: Path):
    cfg = load_config(tmp_path / "nope.yaml")
    assert cfg.lockdown_grace_period_sec == 0
    assert cfg.require_unlock_key is True
    assert cfg.auto_block_unknown is True


def test_overrides_from_yaml(tmp_path: Path):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump({
        "lockdown_grace_period_sec": 10,
        "require_unlock_key": False,
    }))
    cfg = load_config(p)
    assert cfg.lockdown_grace_period_sec == 10
    assert cfg.require_unlock_key is False
    # Untouched keys keep defaults
    assert cfg.auto_block_unknown is True


def test_unknown_keys_are_ignored(tmp_path: Path):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump({
        "lockdown_grace_period_sec": 5,
        "made_up_setting_that_does_not_exist": "boom",
    }))
    cfg = load_config(p)
    assert cfg.lockdown_grace_period_sec == 5
    # Did not crash on unknown key
    assert not hasattr(cfg, "made_up_setting_that_does_not_exist")


def test_empty_file_falls_back_to_defaults(tmp_path: Path):
    p = tmp_path / "config.yaml"
    p.write_text("")
    cfg = load_config(p)
    assert cfg == Config()
