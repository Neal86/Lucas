from types import SimpleNamespace

import pytest

from gpt_windows_connector.gateway import NodeRegistry


def test_control_lock_blocks_other_context_until_released():
    registry = NodeRegistry()
    registry.nodes["Office-PC"] = SimpleNamespace()
    first = registry.acquire_control("Office-PC", "user-a", "Project-A", ttl_seconds=60)
    assert first["context"] == "Project-A"
    registry.acquire_control("Office-PC", "user-a", "Project-A", ttl_seconds=60)
    with pytest.raises(RuntimeError):
        registry.acquire_control("Office-PC", "user-a", "Project-B", ttl_seconds=60)
    with pytest.raises(RuntimeError):
        registry.acquire_control("Office-PC", "user-b", "Project-A", ttl_seconds=60)
    assert registry.release_control("Office-PC", "user-a", "Project-A")["released"] is True
    assert registry.acquire_control("Office-PC", "user-b", "Project-B", ttl_seconds=60)["context"] == "Project-B"
