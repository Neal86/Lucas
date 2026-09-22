from __future__ import annotations

from typing import Any, Callable

from .plugin_host import normalize_plugin_descriptor


class PluginToolService:
    """Account-scoped plugin management and MCP invocation.

    This module keeps plugin orchestration out of gateway.py. Synced metadata never
    grants local Windows permissions, and plugin credentials are not sourced from
    ChatGPT private storage.
    """

    def __init__(self, store, host, audit: Callable[..., None], request_source: Callable[[], dict[str, Any]]) -> None:
        self.store = store
        self.host = host
        self.audit = audit
        self.request_source = request_source

    async def call(
        self,
        user,
        action: str,
        plugin_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> object:
        payload = dict(params or {})
        allowed = {"list", "get", "install", "update", "delete", "list_tools", "call"}
        if action not in allowed:
            raise ValueError(f"Unsupported plugin action: {action}")

        if action == "list":
            return self.store.list(user.id)
        if action == "install":
            normalized = normalize_plugin_descriptor(payload)
            plugin = self.store.upsert(user.id, normalized)
            self.audit(user.id, "plugin.install", plugin["plugin_id"], {"server_url": plugin["server_url"]})
            return plugin

        if not plugin_id:
            raise ValueError("plugin_id is required")
        plugin_id = str(plugin_id).strip()

        if action == "get":
            return self.store.get(user.id, plugin_id)
        if action == "delete":
            if not self.store.remove(user.id, plugin_id):
                raise KeyError("Plugin integration not found")
            self.audit(user.id, "plugin.delete", plugin_id)
            return {"ok": True}
        if action == "update":
            existing = self.store.get(user.id, plugin_id)
            normalized = normalize_plugin_descriptor({**existing, **payload, "plugin_id": plugin_id})
            plugin = self.store.upsert(user.id, normalized)
            self.audit(user.id, "plugin.update", plugin_id)
            return plugin

        plugin = next((item for item in self.store.list(user.id) if item["plugin_id"] == plugin_id), None)
        if not plugin:
            raise KeyError("Plugin integration not found")
        if not plugin.get("enabled", True):
            raise PermissionError("Plugin integration is disabled")

        source = self.request_source()
        agent_id = str(source.get("client_id") or "").strip()
        permissions = plugin.get("agent_permissions") if isinstance(plugin.get("agent_permissions"), dict) else {}
        if agent_id and agent_id in permissions and not bool(permissions[agent_id]):
            raise PermissionError("This AI connection is not allowed to use the plugin")

        if action == "list_tools":
            return await self.host.list_tools(str(plugin["server_url"]))

        tool_name = str(payload.get("tool_name") or "").strip()
        if not tool_name:
            raise ValueError("tool_name is required")
        arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
        self.audit(user.id, "plugin.call", plugin_id, {"tool_name": tool_name, "client_id": agent_id})
        return await self.host.call_tool(str(plugin["server_url"]), tool_name, arguments)
