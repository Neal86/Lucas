from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

class NodeAuthStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    token TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    allowed_roots TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(nodes)").fetchall()}
            if "allowed_roots" not in columns:
                db.execute("ALTER TABLE nodes ADD COLUMN allowed_roots TEXT NOT NULL DEFAULT '[]'")
            if "owner_user_id" in columns or "permission_level" in columns:
                db.execute("ALTER TABLE nodes RENAME TO nodes_legacy")
                db.execute("CREATE TABLE nodes (node_id TEXT PRIMARY KEY, name TEXT NOT NULL, token TEXT NOT NULL, updated_at REAL NOT NULL, allowed_roots TEXT NOT NULL DEFAULT '[]')")
                legacy_cols = {row[1] for row in db.execute("PRAGMA table_info(nodes_legacy)").fetchall()}
                allowed_expr = "allowed_roots" if "allowed_roots" in legacy_cols else "'[]'"
                db.execute(f"INSERT INTO nodes(node_id,name,token,updated_at,allowed_roots) SELECT node_id,name,token,updated_at,{allowed_expr} FROM nodes_legacy")
                db.execute("DROP TABLE nodes_legacy")
            db.execute("CREATE TABLE IF NOT EXISTS user_node_bindings (user_id TEXT NOT NULL, node_id TEXT NOT NULL, approved_at REAL NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY(user_id,node_id))")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    async def record_for(self, node_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM nodes WHERE node_id=?", (node_id,)).fetchone()
        return dict(row) if row else None

    async def save(self, node_id: str, name: str, token: str, allowed_roots: list[str] | None = None) -> None:
        roots_json = json.dumps(allowed_roots or [])
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO nodes(node_id,name,token,updated_at,allowed_roots) VALUES(?,?,?,?,?)
                ON CONFLICT(node_id) DO UPDATE SET name=excluded.name,token=excluded.token,updated_at=excluded.updated_at,allowed_roots=excluded.allowed_roots
                """,
                (node_id, name, token, time.time(), roots_json),
            )

    async def update_token(self, node_id: str, token: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE nodes SET token=?,updated_at=? WHERE node_id=?", (token, time.time(), node_id))

    async def update_config(self, node_id: str, name: str, allowed_roots: list[str]) -> dict:
        with self._connect() as db:
            cur = db.execute("UPDATE nodes SET name=?,allowed_roots=?,updated_at=? WHERE node_id=?", (name, json.dumps(allowed_roots), time.time(), node_id))
            if cur.rowcount != 1:
                raise LookupError("Node not found")
        return await self.record_for(node_id)


class UserNodeBindingStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def node_ids(self, user_id: str) -> list[str]:
        with self._connect() as db:
            return [str(r[0]) for r in db.execute("SELECT node_id FROM user_node_bindings WHERE user_id=? ORDER BY updated_at DESC", (user_id,)).fetchall()]

    def users_for_node(self, node_id: str) -> set[str]:
        with self._connect() as db:
            return {str(r[0]) for r in db.execute("SELECT user_id FROM user_node_bindings WHERE node_id=?", (node_id,)).fetchall()}

    def upsert(self, user_id: str, node_id: str) -> None:
        now = time.time()
        with self._connect() as db:
            db.execute("INSERT INTO user_node_bindings(user_id,node_id,approved_at,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id,node_id) DO UPDATE SET updated_at=excluded.updated_at", (user_id,node_id,now,now))

    def remove(self, user_id: str, node_id: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM user_node_bindings WHERE user_id=? AND node_id=?", (user_id,node_id))

    def reconcile_node(self, node_id: str, authorized_user_ids: list[str]) -> tuple[set[str], set[str]]:
        wanted = {str(v) for v in authorized_user_ids if str(v).strip()}
        current = self.users_for_node(node_id)
        for user_id in wanted:
            self.upsert(user_id, node_id)
        for user_id in current - wanted:
            self.remove(user_id, node_id)
        return wanted - current, current - wanted
