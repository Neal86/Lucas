from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


_SECRET_KEYS = {
    "access_token", "refresh_token", "token", "password", "client_secret",
    "authorization", "cookie", "cookies", "api_key", "apikey", "secret",
}


def _clean_manifest(value: Any) -> Any:
    """Remove credential-like fields before a plugin definition is synchronized."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _SECRET_KEYS or normalized.endswith("_token") or normalized.endswith("_secret"):
                continue
            cleaned[str(key)] = _clean_manifest(item)
        return cleaned
    if isinstance(value, list):
        return [_clean_manifest(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def plugin_identifier(server_url: str, requested: str | None = None) -> str:
    requested = str(requested or "").strip()
    if requested:
        safe = "".join(ch for ch in requested.lower() if ch.isalnum() or ch in "._-")
        if safe:
            return safe[:120]
    normalized = str(server_url or "").strip().rstrip("/").lower()
    if not normalized:
        raise ValueError("server_url is required")
    return "mcp-" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


class PluginSyncStore:
    """Account-level plugin metadata. Local OS permissions and credentials never live here."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _init_db(self) -> None:
        with self._db() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS plugin_integrations(
                    user_id TEXT NOT NULL,
                    plugin_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    server_url TEXT NOT NULL,
                    transport TEXT NOT NULL DEFAULT 'streamable_http',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    manifest_json TEXT NOT NULL DEFAULT '{}',
                    revision INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(user_id, plugin_id)
                );
                CREATE TABLE IF NOT EXISTS plugin_device_state(
                    user_id TEXT NOT NULL,
                    plugin_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    enabled INTEGER,
                    installed_locally INTEGER NOT NULL DEFAULT 0,
                    local_version TEXT,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(user_id, plugin_id, device_id)
                );
                CREATE TABLE IF NOT EXISTS plugin_agent_permissions(
                    user_id TEXT NOT NULL,
                    plugin_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(user_id, plugin_id, agent_id)
                );
                """
            )

    @staticmethod
    def _record(row: sqlite3.Row) -> dict[str, Any]:
        try:
            manifest = json.loads(str(row["manifest_json"] or "{}"))
        except json.JSONDecodeError:
            manifest = {}
        return {
            "plugin_id": str(row["plugin_id"]),
            "name": str(row["name"]),
            "server_url": str(row["server_url"]),
            "transport": str(row["transport"]),
            "enabled": bool(row["enabled"]),
            "manifest": manifest if isinstance(manifest, dict) else {},
            "revision": int(row["revision"] or 1),
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
        }

    def list(self, user_id: str, *, device_id: str | None = None) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM plugin_integrations WHERE user_id=? ORDER BY name COLLATE NOCASE, plugin_id",
                (user_id,),
            ).fetchall()
            device_rows = db.execute(
                "SELECT * FROM plugin_device_state WHERE user_id=? AND device_id=?",
                (user_id, device_id),
            ).fetchall() if device_id else []
            permission_rows = db.execute(
                "SELECT plugin_id,agent_id,enabled FROM plugin_agent_permissions WHERE user_id=?",
                (user_id,),
            ).fetchall()
        devices = {str(row["plugin_id"]): dict(row) for row in device_rows}
        permissions: dict[str, dict[str, bool]] = {}
        for row in permission_rows:
            permissions.setdefault(str(row["plugin_id"]), {})[str(row["agent_id"])] = bool(row["enabled"])
        out = []
        for row in rows:
            item = self._record(row)
            state = devices.get(item["plugin_id"])
            if state:
                item["device"] = {
                    "device_id": str(state["device_id"]),
                    "enabled": None if state["enabled"] is None else bool(state["enabled"]),
                    "installed_locally": bool(state["installed_locally"]),
                    "local_version": state["local_version"],
                    "updated_at": float(state["updated_at"]),
                }
            item["agent_permissions"] = permissions.get(item["plugin_id"], {})
            out.append(item)
        return out

    def get(self, user_id: str, plugin_id: str) -> dict[str, Any]:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM plugin_integrations WHERE user_id=? AND plugin_id=?",
                (user_id, plugin_id),
            ).fetchone()
        if not row:
            raise KeyError("Plugin integration not found")
        return self._record(row)

    def upsert(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        server_url = str(payload.get("server_url") or "").strip()
        if not (server_url.startswith("https://") or server_url.startswith("http://127.0.0.1") or server_url.startswith("http://localhost")):
            raise ValueError("MCP server URL must use HTTPS; localhost is allowed only for local integrations")
        plugin_id = plugin_identifier(server_url, payload.get("plugin_id"))
        name = str(payload.get("name") or plugin_id).strip()[:160] or plugin_id
        transport = str(payload.get("transport") or "streamable_http").strip().lower()
        if transport not in {"streamable_http", "sse", "stdio", "local"}:
            raise ValueError("Unsupported plugin transport")
        manifest = _clean_manifest(payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {})
        now = time.time()
        with self._db() as db:
            existing = db.execute(
                "SELECT created_at,revision FROM plugin_integrations WHERE user_id=? AND plugin_id=?",
                (user_id, plugin_id),
            ).fetchone()
            created_at = float(existing["created_at"]) if existing else now
            revision = int(existing["revision"] or 0) + 1 if existing else 1
            db.execute(
                """INSERT INTO plugin_integrations
                   (user_id,plugin_id,name,server_url,transport,enabled,manifest_json,revision,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(user_id,plugin_id) DO UPDATE SET
                     name=excluded.name,server_url=excluded.server_url,transport=excluded.transport,
                     enabled=excluded.enabled,manifest_json=excluded.manifest_json,
                     revision=excluded.revision,updated_at=excluded.updated_at""",
                (
                    user_id, plugin_id, name, server_url, transport,
                    1 if bool(payload.get("enabled", True)) else 0,
                    json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
                    revision, created_at, now,
                ),
            )
        return self.get(user_id, plugin_id)

    def remove(self, user_id: str, plugin_id: str) -> bool:
        with self._db() as db:
            db.execute("DELETE FROM plugin_device_state WHERE user_id=? AND plugin_id=?", (user_id, plugin_id))
            db.execute("DELETE FROM plugin_agent_permissions WHERE user_id=? AND plugin_id=?", (user_id, plugin_id))
            cursor = db.execute("DELETE FROM plugin_integrations WHERE user_id=? AND plugin_id=?", (user_id, plugin_id))
        return bool(cursor.rowcount)

    def set_device_state(
        self, user_id: str, plugin_id: str, device_id: str, *,
        enabled: bool | None = None, installed_locally: bool = False, local_version: str | None = None,
    ) -> dict[str, Any]:
        self.get(user_id, plugin_id)
        device_id = str(device_id or "").strip()
        if not device_id:
            raise ValueError("device_id is required")
        now = time.time()
        enabled_db = None if enabled is None else (1 if enabled else 0)
        with self._db() as db:
            db.execute(
                """INSERT INTO plugin_device_state(user_id,plugin_id,device_id,enabled,installed_locally,local_version,updated_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(user_id,plugin_id,device_id) DO UPDATE SET
                     enabled=excluded.enabled,installed_locally=excluded.installed_locally,
                     local_version=excluded.local_version,updated_at=excluded.updated_at""",
                (user_id, plugin_id, device_id, enabled_db, 1 if installed_locally else 0, local_version, now),
            )
        return next(item for item in self.list(user_id, device_id=device_id) if item["plugin_id"] == plugin_id)

    def set_agent_permission(self, user_id: str, plugin_id: str, agent_id: str, enabled: bool) -> dict[str, Any]:
        self.get(user_id, plugin_id)
        agent_id = str(agent_id or "").strip()
        if not agent_id:
            raise ValueError("agent_id is required")
        with self._db() as db:
            db.execute(
                """INSERT INTO plugin_agent_permissions(user_id,plugin_id,agent_id,enabled,updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(user_id,plugin_id,agent_id) DO UPDATE SET
                     enabled=excluded.enabled,updated_at=excluded.updated_at""",
                (user_id, plugin_id, agent_id, 1 if enabled else 0, time.time()),
            )
        return self.get(user_id, plugin_id)
