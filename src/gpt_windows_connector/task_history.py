"""Owner-scoped completed task-history totals, independent of display limits.

This projection does not update stored task records, quota or reservations.
Runs and steps retain their existing start-time period attribution.
"""
from __future__ import annotations

import sqlite3
from typing import Any


def completed_task_summary(db: sqlite3.Connection, owner_id: str, *,
                           node_id: str | None = None,
                           since: float | None = None) -> dict[str, int]:
    where = "owner_id=?"
    params: list[Any] = [owner_id]
    if node_id is not None:
        where += " AND node_id=?"
        params.append(node_id)
    if since is not None:
        where += " AND started_at>=?"
        params.append(since)
    # Each aggregate receives exactly the same owner/computer/period scope.
    # One SELECT also keeps the three totals on the same SQLite read snapshot.
    row = db.execute(f"""SELECT
        (SELECT COUNT(*) FROM task_runs WHERE {where}),
        (SELECT COALESCE(SUM(operation_count),0) FROM task_steps WHERE {where}),
        (SELECT COALESCE(SUM(duration_ms),0) FROM task_steps WHERE {where})
        """, params * 3).fetchone()
    return {"task_runs": int(row[0]), "operations": int(row[1]), "duration_ms": int(row[2])}
