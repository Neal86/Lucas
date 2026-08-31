from pathlib import Path

from gpt_windows_connector.access_control import LocalAccessStore, clamp_roots, preset_security


def test_roots_are_clamped_to_node_allowed_roots(tmp_path):
    root = tmp_path / "allowed"
    child = root / "project"
    outside = tmp_path / "outside"
    child.mkdir(parents=True)
    outside.mkdir()
    assert clamp_roots([str(root), str(child), str(outside)], [str(root)]) == [str(root.resolve()), str(child.resolve())]


def test_persistent_user_access_round_trip(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    store = LocalAccessStore(tmp_path / "node-access.json")
    actor = {"user_id": "user-123", "email": "user@example.com", "name": "User"}
    security = preset_security("auto_approve")
    saved = store.upsert(actor, "auto_approve", [str(root)], security=security)
    assert saved["user_id"] == "user-123"
    assert saved["preset"] == "auto_approve"
    effective = store.effective("user-123", [str(root)])
    assert effective is not None
    assert effective["preset"] == "auto_approve"
    assert effective["security"]["approval_policy"]["git_push"] == "always_ask"
    assert effective["allowed_roots"] == [str(root.resolve())]
    assert store.remove("user-123") is True
    assert store.effective("user-123", [str(root)]) is None


def test_full_access_preset_allows_policy_categories():
    security = preset_security("full_access")
    assert all(value == "allow" for value in security["approval_policy"].values())
    assert security["network_external"] == "allow"
    assert security["network_lan"] == "allow"


def test_legacy_admin_access_migrates_to_full_access(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    path = tmp_path / "node-access.json"
    path.write_text('{"version":1,"users":{"legacy":{"permission_level":"admin","allowed_roots":["' + str(root).replace('\\','\\\\') + '"],"enabled":true}}}', encoding="utf-8")
    effective = LocalAccessStore(path).effective("legacy", [str(root)])
    assert effective is not None
    assert effective["preset"] == "full_access"
    assert "permission_level" not in effective


def test_disabled_user_is_denied(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    store = LocalAccessStore(tmp_path / "node-access.json")
    store.upsert({"user_id": "disabled"}, "request_approval", [str(root)], enabled=False)
    assert store.effective("disabled", [str(root)]) is None
