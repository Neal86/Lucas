import json

from gpt_windows_connector.access_control import intersect_security
from gpt_windows_connector import node


def test_user_full_access_cannot_override_node_ask():
    node = {"approval_policy": {"file_delete": "ask"}, "network_external": "block", "network_lan": "allow", "block_silent_network": True}
    user = {"approval_policy": {"file_delete": "allow"}, "network_external": "allow", "network_lan": "allow", "block_silent_network": False}
    effective = intersect_security(node, user)
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
