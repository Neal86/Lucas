from gpt_windows_connector.node import _grants_full_access
from gpt_windows_connector.settings_ui import PRESETS, detect_security_preset, _version_key


def test_settings_ui_uses_autosave_and_folder_checkboxes():
    from pathlib import Path
    text = Path("src/gpt_windows_connector/settings_ui.py").read_text(encoding="utf-8")
    assert "tk.Checkbutton(user_roots" in text
    assert "已自动保存" in text
    assert 'button(fi,"保存更改"' not in text
    assert 'button(user_actions,"保存权限"' not in text
    assert "persist_user_access_if_authorized" in text


def test_full_access_allows_high_risk_actions():
    preset = PRESETS["完全访问权限"]
    assert preset["network_external"] == "allow"
    assert preset["network_lan"] == "allow"
    assert preset["block_silent_network"] is False
    assert all(value == "allow" for value in preset["approval_policy"].values())
    assert preset["approval_policy"]["high_risk"] == "allow"
    assert preset["approval_policy"]["software_install"] == "allow"
    assert preset["approval_policy"]["git_push"] == "allow"


def test_full_access_with_domain_restriction_becomes_custom():
    preset = PRESETS["完全访问权限"]
    assert detect_security_preset(
        dict(preset["approval_policy"]),
        preset["network_external"],
        preset["network_lan"],
        preset["block_silent_network"],
        ["example.com"],
    ) == "自定义"


def test_effective_full_access_uses_actual_policy_not_preset_name():
    preset = PRESETS["完全访问权限"]
    security = {
        "approval_policy": dict(preset["approval_policy"]),
        "network_external": "allow",
        "network_lan": "allow",
        "block_silent_network": False,
        "allowed_domains": [],
    }
    assert _grants_full_access({"preset": "custom", "security": security}) is True
    security["allowed_domains"] = ["example.com"]
    assert _grants_full_access({"preset": "full_access", "security": security}) is False


def test_manual_change_becomes_custom():
    preset = PRESETS["完全访问权限"]
    approvals = dict(preset["approval_policy"])
    approvals["git_push"] = "always_ask"
    assert detect_security_preset(
        approvals,
        preset["network_external"],
        preset["network_lan"],
        preset["block_silent_network"],
    ) == "自定义"


def test_version_comparison_key():
    assert _version_key("1.7.0") > _version_key("1.6.2")
