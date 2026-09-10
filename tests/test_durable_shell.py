from pathlib import Path

from gpt_windows_connector import shell


def test_durable_shell_reuses_completed_request(tmp_path, monkeypatch):
    monkeypatch.setattr(shell, "JOB_ROOT", tmp_path / "jobs")
    first = shell.run_powershell(tmp_path, "Write-Output durable-ok", timeout=20, _request_id="request-123")
    assert first["exit_code"] == 0
    assert "durable-ok" in first["stdout"]
    second = shell.run_powershell(tmp_path, "Write-Output durable-ok", timeout=20, _request_id="request-123")
    assert second["exit_code"] == 0
    assert second["recovered"] is True


def test_durable_shell_refuses_request_id_command_reuse(tmp_path, monkeypatch):
    monkeypatch.setattr(shell, "JOB_ROOT", tmp_path / "jobs")
    shell.run_powershell(tmp_path, "Write-Output one", timeout=20, _request_id="request-456")
    try:
        shell.run_powershell(tmp_path, "Write-Output two", timeout=20, _request_id="request-456")
    except RuntimeError as exc:
        assert "reused for a different command" in str(exc)
    else:
        raise AssertionError("Expected durable request ID reuse to be rejected")


def test_cleanup_jobs_removes_old_completed_and_keeps_live(tmp_path, monkeypatch):
    import json, os, time
    root = tmp_path / "jobs"
    monkeypatch.setattr(shell, "JOB_ROOT", root)
    monkeypatch.setattr(shell, "_LAST_CLEANUP", 0.0)
    old = root / "old"
    live = root / "live"
    old.mkdir(parents=True)
    live.mkdir(parents=True)
    now = time.time()
    (old / "result.json").write_text(json.dumps({"ended_at": now - shell.JOB_RETENTION_SECONDS - 10}), encoding="utf-8")
    (old / "state.json").write_text(json.dumps({"state": "completed"}), encoding="utf-8")
    (live / "state.json").write_text(json.dumps({"state": "running", "pid": os.getpid(), "started_at": now - shell.JOB_STALE_SECONDS - 100}), encoding="utf-8")
    result = shell.cleanup_jobs(force=True, now=now)
    assert result["removed"] == 1
    assert not old.exists()
    assert live.exists()
