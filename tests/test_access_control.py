from pathlib import Path

from gpt_windows_connector.access_control import LocalAccessStore, clamp_permission, clamp_roots


def test_permission_never_exceeds_node_maximum():
    assert clamp_permission("admin", "operate") == "operate"
    assert clamp_permission("operate", "read") == "read"
    assert clamp_permission("read", "admin") == "read"


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
    saved = store.upsert(actor, "admin", [str(root)])
    assert saved["user_id"] == "user-123"
    effective = store.effective("user-123", "operate", [str(root)])
    assert effective is not None
    assert effective["permission_level"] == "operate"
    assert effective["allowed_roots"] == [str(root.resolve())]
    assert store.remove("user-123") is True
    assert store.effective("user-123", "admin", [str(root)]) is None


def test_disabled_user_is_denied(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    store = LocalAccessStore(tmp_path / "node-access.json")
    store.upsert({"user_id": "disabled"}, "read", [str(root)], enabled=False)
    assert store.effective("disabled", "admin", [str(root)]) is None
