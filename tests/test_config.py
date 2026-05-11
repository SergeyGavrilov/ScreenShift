import json
import pytest
from pathlib import Path

import src.config as config_module
from src.config import Config, DEFAULT_CONFIG


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding='utf-8')


# ── loading ───────────────────────────────────────────────────────────────────

def test_loads_existing_config(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    _write(cfg_file, {"autostart": True, "profiles": [{"name": "Work", "hotkey": "ctrl+alt+1", "monitors": {}}]})
    monkeypatch.setattr(config_module, 'CONFIG_PATH', cfg_file)

    cfg = Config()

    assert cfg.autostart is True
    assert len(cfg.profiles) == 1
    assert cfg.profiles[0]['name'] == 'Work'


def test_creates_default_config_when_file_missing(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(config_module, 'CONFIG_PATH', cfg_file)

    cfg = Config()

    assert cfg_file.exists()
    on_disk = json.loads(cfg_file.read_text())
    assert 'profiles' in on_disk
    assert len(cfg.profiles) > 0


def test_default_config_has_two_profiles(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(config_module, 'CONFIG_PATH', cfg_file)

    cfg = Config()

    assert len(cfg.profiles) == len(DEFAULT_CONFIG['profiles'])


# ── autostart ─────────────────────────────────────────────────────────────────

def test_autostart_true(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    _write(cfg_file, {"autostart": True, "profiles": []})
    monkeypatch.setattr(config_module, 'CONFIG_PATH', cfg_file)

    assert Config().autostart is True


def test_autostart_false(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    _write(cfg_file, {"autostart": False, "profiles": []})
    monkeypatch.setattr(config_module, 'CONFIG_PATH', cfg_file)

    assert Config().autostart is False


def test_autostart_missing_defaults_to_false(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    _write(cfg_file, {"profiles": []})
    monkeypatch.setattr(config_module, 'CONFIG_PATH', cfg_file)

    assert Config().autostart is False


# ── profiles ──────────────────────────────────────────────────────────────────

def test_profiles_missing_defaults_to_empty_list(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    _write(cfg_file, {"autostart": False})
    monkeypatch.setattr(config_module, 'CONFIG_PATH', cfg_file)

    assert Config().profiles == []


def test_profile_fields_preserved(tmp_path, monkeypatch):
    profile = {
        "name": "Gaming",
        "hotkey": "ctrl+alt+2",
        "monitors": {"\\\\.\\DISPLAY2": {"enabled": True, "width": 2560, "height": 1440,
                                          "refresh_rate": 144, "position_x": 0, "position_y": 0}},
    }
    cfg_file = tmp_path / "config.json"
    _write(cfg_file, {"autostart": False, "profiles": [profile]})
    monkeypatch.setattr(config_module, 'CONFIG_PATH', cfg_file)

    result = Config().profiles[0]

    assert result['name'] == 'Gaming'
    assert result['hotkey'] == 'ctrl+alt+2'
    assert '\\\\.\\DISPLAY2' in result['monitors']


# ── explicit path arg ─────────────────────────────────────────────────────────

def test_config_accepts_explicit_path(tmp_path):
    cfg_file = tmp_path / "custom.json"
    _write(cfg_file, {"autostart": True, "profiles": []})

    cfg = Config(path=cfg_file)

    assert cfg.autostart is True
