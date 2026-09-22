from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from .auth import current_user
from .plugin_host import normalize_plugin_descriptor
from .plugin_sync import PluginSyncStore


class PluginApi:
    def __init__(self, store: PluginSyncStore, audit) -> None:
        self.store = store
        self.audit = audit

    @staticmethod
    async def _json(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception as exc:
            raise ValueError("A JSON request body is required") from exc
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object")
        return body

    async def collection(self, request: Request):
        user = current_user()
        device_id = str(request.query_params.get("device_id") or "").strip() or None
        if request.method == "GET":
            return JSONResponse({"plugins": self.store.list(user.id, device_id=device_id)})
        try:
            body = await self._json(request)
            normalized = normalize_plugin_descriptor(body)
            plugin = self.store.upsert(user.id, normalized)
            self.audit(user.id, "plugin.upsert", plugin["plugin_id"], {"server_url": plugin["server_url"], "transport": plugin["transport"]})
            return JSONResponse({"plugin": plugin}, status_code=201)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    async def item(self, request: Request):
        user = current_user()
        plugin_id = str(request.path_params.get("plugin_id") or "").strip()
        try:
            if request.method == "GET":
                return JSONResponse({"plugin": self.store.get(user.id, plugin_id)})
            if request.method == "DELETE":
                removed = self.store.remove(user.id, plugin_id)
                if not removed:
                    return JSONResponse({"error": "Plugin integration not found"}, status_code=404)
                self.audit(user.id, "plugin.delete", plugin_id)
                return JSONResponse({"ok": True})
            body = await self._json(request)
            existing = self.store.get(user.id, plugin_id)
            merged = {**existing, **body, "plugin_id": plugin_id}
            plugin = self.store.upsert(user.id, normalize_plugin_descriptor(merged))
            self.audit(user.id, "plugin.update", plugin_id)
            return JSONResponse({"plugin": plugin})
        except KeyError:
            return JSONResponse({"error": "Plugin integration not found"}, status_code=404)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    async def device_state(self, request: Request):
        user = current_user()
        plugin_id = str(request.path_params.get("plugin_id") or "").strip()
        try:
            body = await self._json(request)
            plugin = self.store.set_device_state(
                user.id,
                plugin_id,
                str(body.get("device_id") or ""),
                enabled=(None if body.get("enabled") is None else bool(body.get("enabled"))),
                installed_locally=bool(body.get("installed_locally", False)),
                local_version=(str(body.get("local_version") or "").strip() or None),
            )
            self.audit(user.id, "plugin.device_state", plugin_id, {"device_id": str(body.get("device_id") or "")})
            return JSONResponse({"plugin": plugin})
        except KeyError:
            return JSONResponse({"error": "Plugin integration not found"}, status_code=404)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    async def agent_permission(self, request: Request):
        user = current_user()
        plugin_id = str(request.path_params.get("plugin_id") or "").strip()
        try:
            body = await self._json(request)
            agent_id = str(body.get("agent_id") or "").strip()
            plugin = self.store.set_agent_permission(user.id, plugin_id, agent_id, bool(body.get("enabled", True)))
            self.audit(user.id, "plugin.agent_permission", plugin_id, {"agent_id": agent_id, "enabled": bool(body.get("enabled", True))})
            return JSONResponse({"plugin": plugin})
        except KeyError:
            return JSONResponse({"error": "Plugin integration not found"}, status_code=404)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
