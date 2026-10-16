"""Literal-prefix selection for the existing titled task-context key format."""
from __future__ import annotations

import sqlite3


def find_untitled_context_run(db: sqlite3.Connection, owner_id: str,
                              node_id: str, base_context: str) -> sqlite3.Row | None:
    prefix = base_context + "::task::"
    # Probe only a constant LIKE expression to retain this connection's ASCII
    # case policy. INSTR treats %, _, escape markers and embedded NUL as data;
    # unlike escaped LIKE patterns, long contexts do not double in size or hit
    # SQLite's much smaller pattern-length limit. SQLite LOWER keeps the same
    # built-in ASCII-only folding as default LIKE (not Unicode case folding).
    return db.execute("""SELECT * FROM task_runs
        WHERE owner_id=? AND node_id=? AND (
            context_key=? OR CASE WHEN 'a' LIKE 'A'
                THEN instr(lower(context_key),lower(?))
                ELSE instr(context_key,?) END = 1)
        ORDER BY last_activity_at DESC LIMIT 1""",
        (owner_id,node_id,base_context,prefix,prefix)).fetchone()
