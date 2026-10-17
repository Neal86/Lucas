"""Versioned task identity selection, independent of legacy display keys."""
from __future__ import annotations

import sqlite3


def find_untitled_context_run(db: sqlite3.Connection, owner_id: str,
                              node_id: str, base_context: str) -> sqlite3.Row | None:
    # Untitled exact matches remain case-sensitive. Titled candidates preserve
    # the caller connection's existing SQLite LIKE ASCII case policy, without
    # treating delimiters, wildcard characters or embedded NUL as syntax.
    # Legacy (version 0) identities are ambiguous and must never be guessed.
    return db.execute("""SELECT * FROM task_runs
        WHERE owner_id=? AND node_id=? AND identity_version=1 AND (
            (identity_title IS NULL AND identity_context=?) OR
            (identity_title IS NOT NULL AND CASE WHEN 'a' LIKE 'A'
                THEN lower(identity_context)=lower(?)
                ELSE identity_context=? END))
        ORDER BY last_activity_at DESC LIMIT 1""",
        (owner_id,node_id,base_context,base_context,base_context)).fetchone()
