from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectBinding:
    user_id: str
    project_id: str
    workspace: str
    node_id: str
    name: str | None = None


class BindingStore:
    """Persistent per-user project -> Windows node + workspace bindings.

    There is intentionally no conversation binding layer. The unique binding key
    is (user_id, project_id), so different users may use the same project ID.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS project_bindings (
                    user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    name TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(user_id, project_id)
                )
                """
            )

    @staticmethod
    def _binding(row: sqlite3.Row) -> ProjectBinding:
        return ProjectBinding(
            user_id=row["user_id"], project_id=row["project_id"], workspace=row["workspace"],
            node_id=row["node_id"], name=row["name"],
        )

    def set(self, user_id: str, project_id: str, node_id: str, workspace: str, name: str | None = None) -> ProjectBinding:
        user_id = user_id.strip()
        project_id = project_id.strip()
        node_id = node_id.strip()
        workspace = workspace.strip()
        if not user_id or not project_id or not node_id or not workspace:
            raise ValueError("user_id, project_id, node_id and workspace are required")
        now = time.time()
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO project_bindings(user_id,project_id,workspace,node_id,name,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(user_id,project_id) DO UPDATE SET
                    workspace=excluded.workspace,
                    node_id=excluded.node_id,
                    name=excluded.name,
                    updated_at=excluded.updated_at
                """,
                (user_id, project_id, workspace, node_id, name or None, now, now),
            )
        return ProjectBinding(user_id=user_id, project_id=project_id, workspace=workspace, node_id=node_id, name=name or None)

    def get(self, user_id: str, project_id: str) -> ProjectBinding | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT user_id,project_id,workspace,node_id,name FROM project_bindings WHERE user_id=? AND project_id=?",
                (user_id, project_id),
            ).fetchone()
        return self._binding(row) if row else None

    def remove(self, user_id: str, project_id: str) -> bool:
        with self._connect() as db:
            cur = db.execute("DELETE FROM project_bindings WHERE user_id=? AND project_id=?", (user_id, project_id))
            return cur.rowcount > 0

    def list(self, user_id: str) -> list[ProjectBinding]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT user_id,project_id,workspace,node_id,name FROM project_bindings WHERE user_id=? ORDER BY project_id",
                (user_id,),
            ).fetchall()
        return [self._binding(row) for row in rows]
