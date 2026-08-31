from gpt_windows_connector.settings_ui import PRESETS, detect_security_preset, _version_key


def test_full_access_allows_high_risk_actions():
    preset = PRESETS["完全访问权限"]
    assert preset["network_external"] == "allow"
    assert preset["network_lan"] == "allow"
    assert preset["block_silent_network"] is False
    assert all(value == "allow" for value in preset["approval_policy"].values())
    assert preset["approval_policy"]["high_risk"] == "allow"
    assert preset["approval_policy"]["software_install"] == "allow"
    assert preset["approval_policy"]["git_push"] == "allow"


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
