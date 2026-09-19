import json

from gpt_windows_connector.access_control import intersect_security, preset_security, resolve_effective_security
from gpt_windows_connector import node


def test_full_access_skips_routine_node_asks_but_keeps_hard_blocks_and_safety_gates():
    node_security = {
        "approval_policy": {"file_write": "ask", "file_delete": "block", "desktop_control": "ask"},
        "foreground_confirmation": True,
        "network_external": "ask",
        "network_lan": "allow",
        "block_silent_network": True,
    }
    effective = resolve_effective_security(node_security, preset_security("full_access"), "full_access")
    assert effective["approval_policy"]["file_write"] == "allow"
    assert effective["approval_policy"]["file_delete"] == "block"
    assert effective["approval_policy"]["service_control"] == "always_ask"
    assert effective["approval_policy"]["software_install"] == "always_ask"
    assert effective["network_external"] == "allow"
    assert effective["block_silent_network"] is False
    assert effective["foreground_confirmation"] is True


def test_non_full_access_still_uses_stricter_node_policy():
    node_security = {"approval_policy": {"file_delete": "ask"}, "network_external": "block", "network_lan": "allow", "block_silent_network": True}
    user_security = {"approval_policy": {"file_delete": "allow"}, "network_external": "allow", "network_lan": "allow", "block_silent_network": False}
    effective = intersect_security(node_security, user_security)
    assert effective["approval_policy"]["file_delete"] == "ask"
    assert effective["network_external"] == "block"
    assert effective["block_silent_network"] is True


def test_domain_constraints_only_get_narrower():
    node_security = {"allowed_domains": ["example.com", "api.example.com"]}
    user = {"allowed_domains": ["api.example.com", "other.com"]}
    assert intersect_security(node_security, user)["allowed_domains"] == ["api.example.com"]


def test_connection_code_reload_reads_rotated_value(tmp_path, monkeypatch):
    config_file = tmp_path / "node-config.json"
    device_id_file = tmp_path / "node-device-id.txt"
    monkeypatch.setattr(node, "CONFIG_FILE", config_file)
    monkeypatch.setattr(node, "DEVICE_ID_FILE", device_id_file)
    config_file.write_text(json.dumps({"node_id": "test-node", "connection_code": "11112222"}), encoding="utf-8")
    assert node._ensure_connection_code(node._load_config()) == "11112222"
    config_file.write_text(json.dumps({"node_id": "test-node", "connection_code": "33334444"}), encoding="utf-8")
    assert node._ensure_connection_code(node._load_config()) == "33334444"


def test_gateway_restart_errors_do_not_trigger_route_fanout():
    assert node._is_gateway_restart_error(Exception("received 1012 (service restart)"))
    assert node._is_gateway_restart_error(Exception("server rejected WebSocket connection: HTTP 502"))
    assert not node._is_gateway_restart_error(Exception("getaddrinfo failed"))


def test_disconnect_reason_identifies_ping_timeout():
    assert node._disconnect_reason(Exception("1011 internal error keepalive ping timeout")) == "ping_timeout"
    assert node._disconnect_reason(Exception("received 1012 service restart")) == "gateway_restart"
