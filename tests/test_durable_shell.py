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
