from gpt_windows_connector.access_control import intersect_security


def test_user_full_access_cannot_override_node_ask():
    node = {"approval_policy": {"file_delete": "ask"}, "network_external": "block", "network_lan": "allow", "block_silent_network": True}
    user = {"approval_policy": {"file_delete": "allow"}, "network_external": "allow", "network_lan": "allow", "block_silent_network": False}
    effective = intersect_security(node, user)
    assert effective["approval_policy"]["file_delete"] == "ask"
    assert effective["network_external"] == "block"
    assert effective["block_silent_network"] is True


def test_domain_constraints_only_get_narrower():
    node = {"allowed_domains": ["example.com", "api.example.com"]}
    user = {"allowed_domains": ["api.example.com", "other.com"]}
    assert intersect_security(node, user)["allowed_domains"] == ["api.example.com"]
