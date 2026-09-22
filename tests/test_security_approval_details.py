from __future__ import annotations

from gpt_windows_connector.approval_details import describe_approval, safe_command_preview
from gpt_windows_connector.security import LocalSecurityPolicy


def _policy() -> LocalSecurityPolicy:
    return LocalSecurityPolicy({"security": {"approval_policy": {"shell": "allow", "high_risk": "always_ask"}}})


def test_project_directory_cleanup_is_not_mislabeled_as_system_high_risk():
    category = _policy()._category(
        "shell.run",
        {
            "workspace": r"C:\Users\mrwan\universal-pda",
            "command": r"Remove-Item -Recurse -Force C:\Users\mrwan\universal-pda\dist",
        },
    )
    assert category == "shell"


def test_deleting_entire_user_profile_stays_high_risk():
    category = _policy()._category(
        "shell.run",
        {"command": r"Remove-Item -Recurse -Force C:\Users\mrwan"},
    )
    assert category == "high_risk"


def test_deleting_windows_directory_stays_high_risk():
    category = _policy()._category(
        "shell.run",
        {"command": r"Remove-Item -Recurse -Force C:\Windows\Temp"},
    )
    assert category == "high_risk"


def test_high_risk_restart_has_specific_human_description():
    details = describe_approval(
        "high_risk",
        "shell.run",
        {"workspace": r"C:\work", "command": "Restart-Computer -Force"},
        {"task_title": "Apply system update"},
    )
    assert details["operation"] == "重启这台电脑"
    assert "Apply system update" in details["purpose"]
    assert "重启 Windows" in details["risk_reason"]


def test_network_check_explains_target_host():
    details = describe_approval(
        "shell",
        "shell.run",
        {"workspace": r"C:\work", "command": "Invoke-WebRequest https://lucasmcp.com/dashboard"},
        {},
    )
    assert details["operation"] == "访问或检查网络地址（lucasmcp.com）"
    assert "请求未携带任务标题" in details["purpose"]


def test_command_preview_redacts_credentials():
    preview = safe_command_preview(
        "shell.run",
        {
            "command": (
                "curl https://example.com?token=abc123 "
                "-H 'Authorization: Bearer very-secret-token' "
                "password=hunter2 8776067448:AAHjWvm36_6qxkPUfKkIw9bxVqOX2kwXGmU"
            )
        },
    )
    assert "abc123" not in preview
    assert "very-secret-token" not in preview
    assert "hunter2" not in preview
    assert "AAHjWvm36" not in preview
    assert "[REDACTED" in preview
