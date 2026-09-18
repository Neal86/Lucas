from gpt_windows_connector.settings_ui import PRESETS, detect_security_preset, _version_key


def test_settings_ui_uses_autosave_and_folder_checkboxes():
    from pathlib import Path
    text=Path("src/gpt_windows_connector/settings_ui.py").read_text(encoding="utf-8")
    assert "tk.Checkbutton(user_roots" in text and "已自动保存" in text and 'button(fi,"保存更改"' not in text and 'button(user_actions,"保存权限"' not in text and "persist_user_access_if_authorized" in text


def test_full_access_keeps_only_true_high_risk_safety_gates():
    preset=PRESETS["完全访问权限"]; policy=preset["approval_policy"]
    assert preset["network_external"]=="allow" and preset["network_lan"]=="allow" and preset["block_silent_network"] is False
    for key in ("desktop_control","browser_transfer","git_push","file_write","file_delete","process_control","browser_control","git_write","background_control"):
        assert policy[key]=="allow"
    for key in ("high_risk","software_install","registry_system","service_control"):
        assert policy[key]=="always_ask"


def test_domain_restriction_is_never_full_access():
    preset=PRESETS["完全访问权限"]
    assert detect_security_preset(dict(preset["approval_policy"]),preset["network_external"],preset["network_lan"],preset["block_silent_network"],["example.com"]) != "完全访问权限"


def test_full_access_detects_with_git_push_allowed():
    preset=PRESETS["完全访问权限"]; approvals=dict(preset["approval_policy"])
    assert approvals["git_push"]=="allow"
    assert detect_security_preset(approvals,preset["network_external"],preset["network_lan"],preset["block_silent_network"]) == "完全访问权限"


def test_version_comparison_key():
    assert _version_key("1.7.0") > _version_key("1.6.2")
