import asyncio
from types import SimpleNamespace

import pytest

from gpt_windows_connector.gateway_registry import NodeRegistry, NodeConnection


class FakeSocket:
    async def send_json(self, payload):
        self.last_payload = payload


def test_rpc_timeout_identifies_node_method_and_cleans_pending():
    asyncio.run(_check_timeout())


async def _check_timeout():
    registry = NodeRegistry()
    registry.nodes["node-test"] = NodeConnection(
        node_id="node-test", name="test", allowed_roots=[], websocket=FakeSocket()
    )
    with pytest.raises(TimeoutError, match=r"node=node-test, method=shell.run, request_id="):
        await registry.rpc(
            "node-test", "user-test", "shell.run",
            {"workspace": "C:\\test", "command": "echo hello"},
            timeout=0.02,
        )
    assert "node-test" not in registry.pending_requests
    assert "node-test" not in registry.pending_payloads
