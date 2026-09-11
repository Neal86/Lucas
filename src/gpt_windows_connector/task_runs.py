from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


class TaskRunStore:
    """SQLite-backed Lucas task/subtask timing store."""

    def __init__(self, path: Path, idle_seconds: float = 300.0) -> None:
        self.path = Path(path)
        self.idle_seconds = float(idle_seconds)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS task_runs (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, node_id TEXT NOT NULL,
                context_key TEXT NOT NULL, title TEXT NOT NULL, started_at REAL NOT NULL,
                last_activity_at REAL NOT NULL, ended_at REAL,
                success_count INTEGER NOT NULL DEFAULT 0, error_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_task_runs_owner_started ON task_runs(owner_id, started_at DESC);
            CREATE INDEX IF NOT EXISTS idx_task_runs_active ON task_runs(owner_id,node_id,context_key,last_activity_at DESC);
            CREATE TABLE IF NOT EXISTS task_steps (
                id TEXT PRIMARY KEY, task_run_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                node_id TEXT NOT NULL, action TEXT NOT NULL, target TEXT, status TEXT NOT NULL,
                started_at REAL NOT NULL, ended_at REAL NOT NULL, duration_ms INTEGER NOT NULL,
                operation_count INTEGER NOT NULL DEFAULT 1,
                details TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_task_steps_run_started ON task_steps(task_run_id, started_at ASC);
            """)
            step_columns = {row[1] for row in db.execute("PRAGMA table_info(task_steps)").fetchall()}
            if "operation_count" not in step_columns:
                db.execute("ALTER TABLE task_steps ADD COLUMN operation_count INTEGER NOT NULL DEFAULT 1")

    @staticmethod
    def _title(action: str, target: str | None) -> str:
        clean = str(target or "").strip()
        if clean:
            try: name = Path(clean).name
            except Exception: name = clean
            if name: return f"{action} · {name}"
        return action or "Lucas task"

    def record_operation(self, *, owner_id: str, node_id: str, action: str,
                         target: str | None, started_at: float, ended_at: float,
                         status: str, details: dict[str, Any] | None = None,
                         operation_count: int = 1, context_key: str | None = None,
                         task_title: str | None = None) -> str:
        owner_id=str(owner_id or "local"); node_id=str(node_id or "unknown")
        action=str(action or "operation"); target=str(target or "") or None
        task_title=" ".join(str(task_title or "").split())[:180] or None
        base_context=str(context_key or target or "default")
        titled_context=f"{base_context}::task::{task_title}" if task_title else None
        started_at=float(started_at); ended_at=max(started_at,float(ended_at))
        duration_ms=max(0,round((ended_at-started_at)*1000))
        operation_count=max(1,int(operation_count or 1))
        with self._connect() as db:
            if task_title:
                row=db.execute("SELECT * FROM task_runs WHERE owner_id=? AND node_id=? AND context_key=? ORDER BY last_activity_at DESC LIMIT 1",(owner_id,node_id,titled_context)).fetchone()
                if not row:
                    fallback=db.execute("SELECT * FROM task_runs WHERE owner_id=? AND node_id=? AND context_key=? ORDER BY last_activity_at DESC LIMIT 1",(owner_id,node_id,base_context)).fetchone()
                    if fallback and ended_at-float(fallback["last_activity_at"]) <= self.idle_seconds:
                        db.execute("UPDATE task_runs SET context_key=?,title=? WHERE id=?",(titled_context,task_title,str(fallback["id"])))
                        row=db.execute("SELECT * FROM task_runs WHERE id=?",(str(fallback["id"]),)).fetchone()
            else:
                row=db.execute("SELECT * FROM task_runs WHERE owner_id=? AND node_id=? AND (context_key=? OR context_key LIKE ?) ORDER BY last_activity_at DESC LIMIT 1",(owner_id,node_id,base_context,f"{base_context}::task::%")).fetchone()
            context_key=titled_context or base_context
            if row and ended_at-float(row["last_activity_at"]) <= self.idle_seconds:
                run_id=str(row["id"])
                if task_title and str(row["title"]) != task_title:
                    db.execute("UPDATE task_runs SET title=?,context_key=? WHERE id=?",(task_title,titled_context,run_id))
            else:
                run_id=uuid.uuid4().hex
                db.execute("INSERT INTO task_runs(id,owner_id,node_id,context_key,title,started_at,last_activity_at,ended_at) VALUES(?,?,?,?,?,?,?,?)",(run_id,owner_id,node_id,context_key,task_title or self._title(action,target),started_at,ended_at,ended_at))
            success=status=="success"
            db.execute("UPDATE task_runs SET last_activity_at=?,ended_at=?,success_count=success_count+?,error_count=error_count+? WHERE id=?",(ended_at,ended_at,1 if success else 0,0 if success else 1,run_id))
            db.execute("INSERT INTO task_steps(id,task_run_id,owner_id,node_id,action,target,status,started_at,ended_at,duration_ms,operation_count,details) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(uuid.uuid4().hex,run_id,owner_id,node_id,action,target,status,started_at,ended_at,duration_ms,operation_count,json.dumps(details or {},ensure_ascii=False)))
        return run_id

    def list_runs(self, owner_id: str, *, node_id: str | None=None, limit: int=100, since: float | None=None) -> list[dict[str,Any]]:
        owner_id=str(owner_id or "local"); limit=max(1,min(int(limit),500))
        where="owner_id=?"; params:list[Any]=[owner_id]
        if node_id: where+=" AND node_id=?"; params.append(str(node_id))
        if since is not None: where+=" AND started_at>=?"; params.append(float(since))
        params.append(limit)
        with self._connect() as db:
            rows=db.execute(f"SELECT * FROM task_runs WHERE {where} ORDER BY started_at DESC LIMIT ?",params).fetchall()
            out=[]; now=time.time()
            for row in rows:
                item=dict(row); last=float(item["last_activity_at"])
                item["status"]="running" if now-last <= self.idle_seconds else ("failed" if int(item["error_count"]) and not int(item["success_count"]) else "completed")
                end=now if item["status"]=="running" else float(item["ended_at"] or last)
                item["duration_ms"]=max(0,round((end-float(item["started_at"]))*1000))
                steps=[]
                for step in db.execute("SELECT * FROM task_steps WHERE task_run_id=? ORDER BY started_at ASC",(item["id"],)).fetchall():
                    sub=dict(step)
                    try: sub["details"]=json.loads(sub.get("details") or "{}")
                    except Exception: sub["details"]={}
                    steps.append(sub)
                item["steps"]=steps; out.append(item)
        return out
