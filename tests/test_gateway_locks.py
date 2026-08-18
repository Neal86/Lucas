from types import SimpleNamespace

import pytest

from gpt_windows_connector.gateway import NodeRegistry


def test_control_lock_blocks_other_project():
    registry = NodeRegistry()
    registry.nodes["Office-PC"] = SimpleNamespace(owner_user_id="user-a")
    first = registry.acquire_control("Office-PC", "user-a", "Project-A", ttl_seconds=60)
    assert first["project_id"] == "Project-A"
    registry.acquire_control("Office-PC", "user-a", "Project-A", ttl_seconds=60)
    with pytest.raises(RuntimeError):
        registry.acquire_control("Office-PC", "user-a", "Project-B", ttl_seconds=60)
    with pytest.raises(PermissionError):
        registry.acquire_control("Office-PC", "user-b", "Project-A", ttl_seconds=60)
    assert registry.release_control("Office-PC", "user-a", "Project-A")["released"] is True
    assert registry.acquire_control("Office-PC", "user-a", "Project-B", ttl_seconds=60)["project_id"] == "Project-B"
