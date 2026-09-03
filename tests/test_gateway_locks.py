from pathlib import Path
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


def test_gateway_does_not_duplicate_node_workspace_validation():
    source = (Path(__file__).resolve().parents[1] / "src" / "gpt_windows_connector" / "gateway.py").read_text(encoding="utf-8")
    node_rpc = source.split("async def _node_rpc", 1)[1].split("async def _desktop_lock", 1)[0]
    desktop_lock = source.split("async def _desktop_lock", 1)[1].split("def _client_ip", 1)[0]
    control_acquire = source.split("async def control_acquire", 1)[1].split("@mcp.tool()", 1)[0]
    assert 'registry.rpc(node_id, user.id, "workspace.info"' not in node_rpc
    assert 'registry.rpc(node_id, user.id, "workspace.info"' not in desktop_lock
    assert 'registry.rpc(node_id, user.id, "workspace.info"' not in control_acquire
    assert 'payload["workspace"] = workspace' in node_rpc
