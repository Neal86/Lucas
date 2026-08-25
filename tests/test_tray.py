from pathlib import Path

from gpt_windows_connector import tray


def test_tray_defaults_enabled():
    assert tray._connection_enabled({}) is True
    assert tray._startup_enabled({}) is True


def test_tray_respects_disabled_flags():
    config = {"connection_enabled": False, "launch_at_startup": False}
    assert tray._connection_enabled(config) is False
    assert tray._startup_enabled(config) is False


def test_json_round_trip(tmp_path: Path):
    target = tmp_path / "status.json"
    payload = {"status": "Online", "detail": "", "time": 1.0}
    tray._save_json(target, payload)
    assert tray._load_json(target) == payload
