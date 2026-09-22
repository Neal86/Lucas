from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from .credential_vault import protect_text, unprotect_text


class LocalAccountClient:
    """Authenticated Lucas account client used by the local desktop app.

    The account token is protected with Windows DPAPI. Plugin metadata is cached
    separately so credentials and local OS permissions are never synchronized as
    ordinary JSON.
    """

    def __init__(self, base_url: str, state_path: Path, plugin_cache_path: Path) -> None:
        self.base_url = self._normalize_base_url(base_url)
        self.state_path = Path(state_path)
        self.plugin_cache_path = Path(plugin_cache_path)

    @staticmethod
    def _normalize_base_url(value: str) -> str:
        raw = str(value or "").strip()
        if raw.startswith("wss://"):
            raw = "https://" + raw[6:]
        elif raw.startswith("ws://"):
            raw = "http://" + raw[5:]
        raw = raw.rstrip("/")
        if raw.endswith("/ws/node"):
            raw = raw[:-8]
        parsed = urlparse(raw)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError("Invalid Lucas account server URL")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("Lucas account server must use HTTPS")
        return raw

    def _read_state(self) -> dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_state(self, data: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_path.with_name(f"{self.state_path.name}.{os.getpid()}.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.state_path)

    def _token(self) -> str:
        protected = str(self._read_state().get("access_token_dpapi") or "")
        if not protected:
            return ""
        try:
            return unprotect_text(protected)
        except Exception:
            return ""

    def status(self) -> dict[str, Any]:
        state = self._read_state()
        return {
            "signed_in": bool(self._token()),
            "email": str(state.get("email") or ""),
            "name": str(state.get("name") or ""),
            "user_id": str(state.get("user_id") or ""),
            "last_sync_at": state.get("last_sync_at"),
        }

    def login(self, email: str, password: str, timeout: float = 20.0) -> dict[str, Any]:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                self.base_url + "/auth/login",
                json={"email": str(email or "").strip(), "password": str(password or "")},
            )
        if response.status_code >= 400:
            try:
                message = str(response.json().get("error") or "Sign in failed")
            except Exception:
                message = "Sign in failed"
            raise PermissionError(message)
        payload = response.json()
        token = str(payload.get("access_token") or "")
        user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
        if not token:
            raise PermissionError("Lucas did not return an account token")
        state = {
            "access_token_dpapi": protect_text(token),
            "user_id": str(user.get("id") or ""),
            "email": str(user.get("email") or email or ""),
            "name": str(user.get("name") or ""),
            "provider": str(user.get("provider") or ""),
            "last_sync_at": None,
        }
        self._write_state(state)
        return self.status()

    def logout(self) -> None:
        try:
            self.state_path.unlink(missing_ok=True)
        finally:
            try:
                self.plugin_cache_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _headers(self) -> dict[str, str]:
        token = self._token()
        if not token:
            raise PermissionError("Sign in to Lucas first")
        return {"Authorization": f"Bearer {token}"}

    def me(self, timeout: float = 15.0) -> dict[str, Any]:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(self.base_url + "/auth/me", headers=self._headers())
        if response.status_code == 401:
            self.logout()
            raise PermissionError("Lucas account session expired")
        response.raise_for_status()
        return dict(response.json().get("user") or {})

    def sync_plugins(self, device_id: str, timeout: float = 20.0) -> list[dict[str, Any]]:
        device_id = str(device_id or "").strip()
        if not device_id:
            raise ValueError("device_id is required")
        with httpx.Client(timeout=timeout) as client:
            response = client.get(
                self.base_url + "/api/plugins",
                params={"device_id": device_id},
                headers=self._headers(),
            )
        if response.status_code == 401:
            self.logout()
            raise PermissionError("Lucas account session expired")
        response.raise_for_status()
        plugins = response.json().get("plugins") or []
        if not isinstance(plugins, list):
            plugins = []
        safe_plugins = [item for item in plugins if isinstance(item, dict)]
        self.plugin_cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.plugin_cache_path.with_name(f"{self.plugin_cache_path.name}.{os.getpid()}.tmp")
        temp.write_text(json.dumps({"plugins": safe_plugins}, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.plugin_cache_path)
        state = self._read_state()
        import time
        state["last_sync_at"] = time.time()
        self._write_state(state)
        return safe_plugins

    def install_plugin(self, name: str, server_url: str, timeout: float = 20.0) -> dict[str, Any]:
        payload = {"name": str(name or "").strip() or "MCP Integration", "server_url": str(server_url or "").strip()}
        with httpx.Client(timeout=timeout) as client:
            response = client.post(self.base_url + "/api/plugins", json=payload, headers=self._headers())
        if response.status_code == 401:
            self.logout()
            raise PermissionError("Lucas account session expired")
        if response.status_code >= 400:
            try:
                raise ValueError(str(response.json().get("error") or "Could not add integration"))
            except (ValueError, TypeError):
                raise
            except Exception as exc:
                raise ValueError("Could not add integration") from exc
        plugin = response.json().get("plugin") or {}
        return dict(plugin) if isinstance(plugin, dict) else {}

    def remove_plugin(self, plugin_id: str, timeout: float = 20.0) -> None:
        plugin_id = str(plugin_id or "").strip()
        if not plugin_id:
            raise ValueError("plugin_id is required")
        with httpx.Client(timeout=timeout) as client:
            response = client.delete(self.base_url + f"/api/plugins/{plugin_id}", headers=self._headers())
        if response.status_code == 401:
            self.logout()
            raise PermissionError("Lucas account session expired")
        if response.status_code >= 400:
            try:
                message = str(response.json().get("error") or "Could not remove integration")
            except Exception:
                message = "Could not remove integration"
            raise ValueError(message)

    def cached_plugins(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.plugin_cache_path.read_text(encoding="utf-8"))
            plugins = data.get("plugins") if isinstance(data, dict) else []
            return [item for item in (plugins or []) if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError):
            return []
