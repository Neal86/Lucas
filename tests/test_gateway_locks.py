import pytest

from gpt_windows_connector.gateway import NodeRegistry


def test_control_lock_blocks_other_project():
    registry = NodeRegistry()
    registry.nodes["Office-PC"] = object()  # acquire_control only requires online presence
    first = registry.acquire_control("Office-PC", "Project-A", ttl_seconds=60)
    assert first["project_id"] == "Project-A"
    registry.acquire_control("Office-PC", "Project-A", ttl_seconds=60)
    with pytest.raises(RuntimeError):
        registry.acquire_control("Office-PC", "Project-B", ttl_seconds=60)
    assert registry.release_control("Office-PC", "Project-A")["released"] is True
    assert registry.acquire_control("Office-PC", "Project-B", ttl_seconds=60)["project_id"] == "Project-B"
