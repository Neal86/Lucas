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


def test_tray_reads_powershell_utf8_bom_json(tmp_path: Path):
    target = tmp_path / "node-config.json"
    target.write_text('{"connection_code":"12345678"}', encoding="utf-8-sig")
    assert tray._load_json(target)["connection_code"] == "12345678"


def test_reconnecting_status_for_current_process_requests_recovery():
    assert tray._status_requests_recovery({"status": "Reconnecting", "pid": 42}, 42) is True
    assert tray._status_requests_recovery({"status": "Online", "pid": 42}, 42) is False
    assert tray._status_requests_recovery({"status": "Reconnecting", "pid": 41}, 42) is False


def test_supervisor_gap_detects_system_resume():
    assert tray._supervisor_gap_requires_recovery(2.0) is False
    assert tray._supervisor_gap_requires_recovery(tray.RESUME_GAP_SECONDS) is False
    assert tray._supervisor_gap_requires_recovery(tray.RESUME_GAP_SECONDS + 0.1) is True


def test_stale_status_watchdog_recovers_reconnecting_node_after_startup_grace():
    assert tray._stale_status_requires_recovery(tray.STATUS_STALE_SECONDS + 1, tray.NODE_STARTUP_GRACE_SECONDS + 1) is True
    assert tray._stale_status_requires_recovery(tray.STATUS_STALE_SECONDS + 1, tray.NODE_STARTUP_GRACE_SECONDS - 1) is False
    assert tray._stale_status_requires_recovery(tray.STATUS_STALE_SECONDS - 1, tray.NODE_STARTUP_GRACE_SECONDS + 1) is False
