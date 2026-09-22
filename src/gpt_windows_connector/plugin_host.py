from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PluginDescriptor:
    plugin_id: str
    name: str
    server_url: str
    transport: str = "streamable_http"
    manifest: dict[str, Any] | None = None


def normalize_plugin_descriptor(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize OpenAI/MCP-style plugin metadata into Lucas' portable record.

    Lucas deliberately synchronizes only metadata here. OAuth/client secrets,
    cookies and local OS permissions remain outside the portable record.
    """
    if not isinstance(payload, dict):
        raise ValueError("Plugin descriptor must be an object")

    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else dict(payload)
    mcp = manifest.get("mcp") if isinstance(manifest.get("mcp"), dict) else {}
    server = (
        payload.get("server_url")
        or mcp.get("url")
        or mcp.get("server_url")
        or manifest.get("mcp_url")
        or manifest.get("server_url")
        or manifest.get("url")
    )
    server_url = str(server or "").strip()
    if not server_url:
        raise ValueError("Plugin descriptor does not include an MCP server URL")

    raw_name = (
        payload.get("name")
        or manifest.get("name")
        or manifest.get("display_name")
        or manifest.get("title")
        or "MCP Integration"
    )
    transport = str(
        payload.get("transport")
        or mcp.get("transport")
        or manifest.get("transport")
        or "streamable_http"
    ).strip().lower().replace("-", "_")
    if transport in {"http", "streamablehttp"}:
        transport = "streamable_http"

    return {
        "plugin_id": str(payload.get("plugin_id") or manifest.get("id") or "").strip() or None,
        "name": str(raw_name).strip()[:160] or "MCP Integration",
        "server_url": server_url,
        "transport": transport,
        "enabled": bool(payload.get("enabled", True)),
        "manifest": manifest,
    }


class RemoteMcpPluginHost:
    """Small compatibility host for standard remote MCP servers.

    Auth headers are supplied per call by the local/device credential layer; they
    are never read from synchronized plugin metadata.
    """

    async def _session(self, server_url: str, headers: dict[str, str] | None = None):
        from contextlib import AsyncExitStack

        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        stack = AsyncExitStack()
        read_stream, write_stream, _ = await stack.enter_async_context(
            streamablehttp_client(server_url, headers=dict(headers or {}))
        )
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        return stack, session

    async def list_tools(self, server_url: str, headers: dict[str, str] | None = None) -> list[dict[str, Any]]:
        stack, session = await self._session(server_url, headers)
        try:
            response = await session.list_tools()
            out: list[dict[str, Any]] = []
            for tool in getattr(response, "tools", []) or []:
                out.append({
                    "name": str(getattr(tool, "name", "")),
                    "description": str(getattr(tool, "description", "") or ""),
                    "input_schema": getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {},
                })
            return out
        finally:
            await stack.aclose()

    async def call_tool(
        self,
        server_url: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        stack, session = await self._session(server_url, headers)
        try:
            result = await session.call_tool(str(tool_name), dict(arguments or {}))
            if hasattr(result, "model_dump"):
                return result.model_dump(mode="json")
            return result
        finally:
            await stack.aclose()
