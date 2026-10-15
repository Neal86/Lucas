"""Risk gates combine with operation policy; all OS effects are harmless stubs."""
import asyncio

import pytest

from gpt_windows_connector import computer, processes
from gpt_windows_connector.access_control import preset_security
from gpt_windows_connector.executor import Executor
from gpt_windows_connector.security import LocalSecurityPolicy


CASES = [
    ("Restart-Computer", "high_risk", "powershell"),
    ("winget install Test.Package", "software_install", "powershell"),
    (r"reg add HKCU\Software\Example", "registry_system", "cmd"),
    ("Stop-Service ExampleService", "service_control", "pwsh"),
    ("winget.exe install Test.Package", "software_install", "cmd.exe"),
    ("SC.EXE stop ExampleService", "service_control", "cmd"),
    ("shutdown.exe /r /t 0", "high_risk", "cmd"),
    ('powershell.exe -Command "Restart-Computer"', "high_risk", "cmd"),
]


@pytest.mark.parametrize("preset", ["auto_approve", "full_access"])
@pytest.mark.parametrize("command,category,shell_type", CASES)
def test_process_start_requires_detected_risk_approval(tmp_path, monkeypatch, preset, command, category, shell_type):
    executor = Executor((tmp_path,), {"security": preset_security(preset)})
    prompts, calls = [], []
    monkeypatch.setattr(executor.security, "_prompt", lambda *args: prompts.append(args) or False)
    monkeypatch.setattr(processes, "start_process", lambda *args, **kwargs: calls.append(kwargs))
    with pytest.raises(PermissionError):
        asyncio.run(executor.call("process.start", {"workspace": str(tmp_path), "command": command, "shell_type": shell_type}))
    assert calls == [] and prompts
    assert category in prompts[0][0] or category in executor.security.audit_decisions[-1]["category"]


@pytest.mark.parametrize("blocked", ["process_control", "high_risk", "software_install", "service_control"])
def test_compound_process_obeys_every_explicit_block_without_prompt(monkeypatch, blocked):
    settings = preset_security("full_access")
    settings["approval_policy"][blocked] = "block"
    security = LocalSecurityPolicy({"security": settings})
    monkeypatch.setattr(security, "_prompt", lambda *args: pytest.fail("Explicit block must precede a prompt"))
    with pytest.raises(PermissionError, match="Blocked"):
        security.authorize("process.start", {"command": "winget install Test.Package; Stop-Service Example; Restart-Computer"})


def test_approved_dangerous_process_runs_once_and_always_asks_again(tmp_path, monkeypatch):
    executor = Executor((tmp_path,), {"security": preset_security("auto_approve")})
    prompts, calls = [], []
    monkeypatch.setattr(executor.security, "_prompt", lambda *args: prompts.append(args) or True)
    monkeypatch.setattr(processes, "start_process", lambda *args, **kwargs: calls.append(kwargs) or {"ok": True})
    for _ in range(2):
        assert asyncio.run(executor.call("process.start", {"workspace": str(tmp_path), "command": "Restart-Computer"})) == {"ok": True}
    assert len(prompts) == len(calls) == 2


def test_normal_process_and_stop_keep_existing_policy(tmp_path, monkeypatch):
    executor = Executor((tmp_path,), {"security": preset_security("auto_approve")})
    monkeypatch.setattr(executor.security, "_prompt", lambda *args: pytest.fail("Ordinary allowed process should not prompt"))
    monkeypatch.setattr(processes, "start_process", lambda *args, **kwargs: {"process_id": "test-process"})
    monkeypatch.setattr(processes, "stop_process", lambda *args, **kwargs: {"stopped": True})
    assert asyncio.run(executor.call("process.start", {"workspace": str(tmp_path), "command": "python --version"})) == {"process_id": "test-process"}
    assert asyncio.run(executor.call("process.stop", {"workspace": str(tmp_path), "process_id": "test-process"})) == {"stopped": True}


@pytest.mark.parametrize("confirmation", [True, False])
@pytest.mark.parametrize("method,params", [("computer.click", {}), ("computer.ui_click", {"allow_foreground_fallback": True}), ("browser.launch_persistent", {"headless": False})])
def test_desktop_block_precedes_focus_toggle(monkeypatch, confirmation, method, params):
    settings = preset_security("full_access")
    settings["foreground_confirmation"] = confirmation
    settings["approval_policy"]["desktop_control"] = "block"
    security = LocalSecurityPolicy({"security": settings})
    monkeypatch.setattr(security, "_prompt", lambda *args: pytest.fail("Explicit block must not ask"))
    with pytest.raises(PermissionError, match="Blocked"):
        security.authorize(method, params)


def test_desktop_block_prevents_real_executor_dispatch(tmp_path, monkeypatch):
    settings = preset_security("full_access")
    settings["foreground_confirmation"] = False
    settings["approval_policy"]["desktop_control"] = "block"
    executor = Executor((tmp_path,), {"security": settings})
    monkeypatch.setattr(computer, "click", lambda **kwargs: pytest.fail("Blocked click reached dispatcher"))
    with pytest.raises(PermissionError, match="Blocked"):
        asyncio.run(executor.call("computer.click", {}))


def test_focus_toggle_still_controls_nonblocked_foreground(monkeypatch):
    settings = preset_security("full_access")
    settings["foreground_confirmation"] = False
    security = LocalSecurityPolicy({"security": settings})
    monkeypatch.setattr(security, "_prompt", lambda *args: pytest.fail("Focus confirmation is explicitly disabled"))
    security.authorize("computer.click", {})


@pytest.mark.parametrize("blocked", ["shell", "high_risk", "service_control"])
def test_compound_shell_does_not_hide_a_second_gate(monkeypatch, blocked):
    settings = preset_security("full_access")
    settings["approval_policy"][blocked] = "block"
    security = LocalSecurityPolicy({"security": settings})
    monkeypatch.setattr(security, "_prompt", lambda *args: pytest.fail("All blocks must be resolved before prompting"))
    with pytest.raises(PermissionError, match="Blocked"):
        security.authorize("shell.run", {"command": "winget install Test.Package; Stop-Service Example; Restart-Computer"})
