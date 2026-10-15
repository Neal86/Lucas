"""Durable minimum-operation admission and atomic, idempotent settlement.

SQLite locks cover only local bookkeeping, never a Node RPC. Unconfirmed work
is retained for human review; a deadline changes its label, not its reservation.
No gateway-side retry, release, or reconstruction of lost shell counts occurs.
"""
from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .task_audit import sanitize_task_details

if TYPE_CHECKING:
    from .auth import AuthStore
    from .task_runs import TaskRunStore


def _details(value: Any) -> dict[str, Any]:
    """Persist only the operation metadata contract, never payloads or errors.

    Shell statements become fixed labels. Arbitrary keys/nested values (including
    command, output, exception messages and authentication material) are dropped.
    Identifiers and the user-provided task title retain their existing contract.
    """
    source = sanitize_task_details(value)
    out: dict[str, Any] = {}
    for key in ("agent", "session_id", "task_title"):
        item = source.get(key)
        if key in source and (item is None or isinstance(item, str)):
            out[key] = item[:256] if isinstance(item, str) else None
    if source.get("source") in ("oauth", "account"):
        out["source"] = source["source"]
    error = source.get("error_type")
    if isinstance(error, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", error):
        out["error_type"] = error
    if source.get("reason") == "accounting_failed":
        out["reason"] = "accounting_failed"
    if source.get("confirmed_outcome") in ("success", "failed"):
        out["confirmed_outcome"] = source["confirmed_outcome"]
    if "sub_operations" in source:
        out["sub_operations"] = source["sub_operations"]
    return out


def _has_table(db: sqlite3.Connection, name: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _initialize(db: sqlite3.Connection) -> None:
    # No executescript: it implicitly commits a caller-owned transaction.
    db.execute("""CREATE TABLE IF NOT EXISTS operation_reservations (
        id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, node_id TEXT NOT NULL,
        action TEXT NOT NULL, target TEXT, started_at REAL NOT NULL,
        period_start REAL NOT NULL, period_end REAL NOT NULL,
        deadline_at REAL NOT NULL, reserved_operations INTEGER NOT NULL CHECK(reserved_operations >= 1),
        status TEXT NOT NULL CHECK(status IN ('pending','outcome_unconfirmed','settled')),
        details TEXT NOT NULL DEFAULT '{}', context_key TEXT, task_title TEXT,
        settled_at REAL, outcome TEXT, operation_count INTEGER, task_run_id TEXT
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_operation_reservations_owner_period ON operation_reservations(owner_id,status,started_at)")


@contextmanager
def _transaction(path: Path):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _transition_audit(db: sqlite3.Connection, row: sqlite3.Row, action: str, now: float, *, error_type: str | None = None, metadata: dict[str, Any] | None = None) -> None:
    # Older read-only/projection fixtures may have no audit table yet.
    if not _has_table(db, "audit_logs"):
        return
    details = {"reservation_id": row["id"], "node_id": row["node_id"], "action": row["action"],
               "reserved_operations": row["reserved_operations"]}
    details.update(_details(metadata))
    details.update(_details({"error_type": error_type}))
    db.execute("INSERT INTO audit_logs(user_id,action,target,details,created_at) VALUES(?,?,?,?,?)",
               (row["owner_id"], action, row["target"], json.dumps(details), now))


def _expire_pending(db: sqlite3.Connection, owner_id: str, now: float) -> None:
    rows = db.execute("SELECT * FROM operation_reservations WHERE owner_id=? AND status='pending' AND deadline_at<=?",
                      (owner_id, now)).fetchall()
    for row in rows:
        db.execute("UPDATE operation_reservations SET status='outcome_unconfirmed' WHERE id=? AND status='pending'", (row["id"],))
        _transition_audit(db, row, "operation.outcome_unconfirmed", now, error_type="DeadlineExceeded")


def reservation_counts(db: sqlite3.Connection, owner_id: str, period_start: float, period_end: float, now: float) -> tuple[int, int]:
    """Read within the entitlement caller's transaction; tolerate old databases."""
    if not _has_table(db, "operation_reservations"):
        return 0, 0
    _expire_pending(db, owner_id, now)
    # Use the same current-period admission timestamp rule as completed steps,
    # including paid plan changes that move or overlap a billing window.
    row = db.execute("""SELECT
        COALESCE(SUM(CASE WHEN status='pending' THEN reserved_operations ELSE 0 END),0),
        COALESCE(SUM(CASE WHEN status='outcome_unconfirmed' THEN reserved_operations ELSE 0 END),0)
        FROM operation_reservations WHERE owner_id=? AND status!='settled'
        AND started_at>=? AND started_at<?""",
        (owner_id, period_start, period_end)).fetchone()
    return int(row[0]), int(row[1])


def list_unresolved(db_path: Path, owner_id: str, *, now: float | None = None, limit: int = 100,
                    node_id: str | None = None, since: float | None = None) -> list[dict[str, Any]]:
    """Owner-scoped current and historical unresolved work, with safe metadata."""
    from .entitlements import _plan_state

    with _transaction(db_path) as db:
        if not _has_table(db, "operation_reservations"):
            return []
        now = float(time.time() if now is None else now)
        _expire_pending(db, owner_id, now)
        _, _, _, _, start, end, _, _ = _plan_state(db, owner_id, now)
        where = "owner_id=? AND status!='settled'"
        params: list[Any] = [owner_id]
        if node_id is not None:
            where += " AND node_id=?"
            params.append(str(node_id))
        if since is not None:
            where += " AND started_at>=?"
            params.append(float(since))
        params.append(max(1, min(int(limit), 500)))
        rows = db.execute(f"SELECT * FROM operation_reservations WHERE {where} ORDER BY started_at DESC,id DESC LIMIT ?", params).fetchall()
        result = []
        for row in rows:
            item = {key: row[key] for key in ("id", "owner_id", "node_id", "action", "target", "started_at", "status", "reserved_operations", "period_start", "period_end", "deadline_at")}
            item["currently_held"] = bool(start <= row["started_at"] < end)
            try:
                raw = json.loads(row["details"])
            except (TypeError, ValueError):
                raw = {}
            item["details"] = _details(raw)
            result.append(item)
        return result


class OperationAdmissionStore:
    def __init__(self, db_path: Path, *, auth_store: AuthStore, task_store: TaskRunStore) -> None:
        self.path = Path(db_path)
        self.auth = auth_store
        self.tasks = task_store

    def reserve(self, *, owner_id: str, node_id: str, action: str, target: str | None,
                requested_operations: int = 1, timeout_seconds: float = 180.0,
                details: dict[str, Any] | None = None, context_key: str | None = None,
                task_title: str | None = None) -> dict[str, Any]:
        from .entitlements import ensure_request_capacity

        count = max(1, int(requested_operations or 1))
        timeout = float(timeout_seconds)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Operation timeout must be finite and positive")
        with _transaction(self.path) as db:
            _initialize(db)
            # Sample only AFTER acquiring the cross-process writer lock. Waiting
            # at a month boundary must not reserve against the preceding period.
            started_at = time.time()
            ent = ensure_request_capacity(self.path, owner_id, count, connection=db, now=started_at)
            operation_id = uuid.uuid4().hex
            safe_details = _details(details)
            title = " ".join(str(task_title or "").split())[:180] or None
            db.execute("""INSERT INTO operation_reservations
                (id,owner_id,node_id,action,target,started_at,period_start,period_end,deadline_at,
                 reserved_operations,status,details,context_key,task_title)
                VALUES(?,?,?,?,?,?,?,?,?,?,'pending',?,?,?)""",
                (operation_id, owner_id, node_id, action, target, started_at, ent.period_start, ent.period_end,
                 started_at + timeout, count, json.dumps(safe_details, ensure_ascii=False), context_key, title))
            row = db.execute("SELECT * FROM operation_reservations WHERE id=?", (operation_id,)).fetchone()
            _transition_audit(db, row, "operation.admitted", started_at)
            result = dict(row)
            result["details"] = safe_details
            return result

    def mark_unconfirmed(self, reservation_id: str, *, error_type: str | None = None,
                         reason: str | None = None, confirmed_outcome: str | None = None) -> None:
        with _transaction(self.path) as db:
            row = db.execute("SELECT * FROM operation_reservations WHERE id=?", (reservation_id,)).fetchone()
            if row is None:
                raise KeyError(reservation_id)
            if row["status"] == "settled":
                return
            details = _details(json.loads(row["details"]))
            extra = _details({"error_type": error_type, "reason": reason, "confirmed_outcome": confirmed_outcome})
            if row["status"] == "outcome_unconfirmed":
                # A reader may have expired the reservation before a late known
                # result. Preserve improved evidence if its settlement failed.
                if extra.get("reason") != "accounting_failed" or all(details.get(k) == v for k, v in extra.items()):
                    return
            now = time.time()
            details.update(extra)
            db.execute("UPDATE operation_reservations SET status='outcome_unconfirmed',details=? WHERE id=?", (json.dumps(details), reservation_id))
            audit_action = "operation.accounting_unconfirmed" if details.get("reason") == "accounting_failed" else "operation.outcome_unconfirmed"
            _transition_audit(db, row, audit_action, now, error_type=error_type, metadata=details)

    def settle(self, reservation_id: str, *, status: str = "success", operation_count: int = 1,
               ended_at: float | None = None, duration_seconds: float | None = None,
               details: dict[str, Any] | None = None) -> str:
        if status not in {"success", "failed"}:
            raise ValueError("Settlement requires a confirmed success or failure")
        with _transaction(self.path) as db:
            row = db.execute("SELECT * FROM operation_reservations WHERE id=?", (reservation_id,)).fetchone()
            if row is None:
                raise KeyError(reservation_id)
            if row["status"] == "settled":
                # First confirmed completion is immutable, even if later callers
                # supply a different outcome, weight, timestamp, or metadata.
                return str(row["task_run_id"])
            end = max(float(row["started_at"]), float(time.time() if ended_at is None else ended_at))
            duration = max(0.0, end - row["started_at"] if duration_seconds is None else float(duration_seconds))
            count = max(int(row["reserved_operations"]), int(operation_count or 1))
            safe_details = _details(json.loads(row["details"]))
            # Transitional uncertainty stays in its audit events; completed
            # outcomes must not retain a stale timeout/accounting-error label.
            for key in ("error_type", "reason", "confirmed_outcome"):
                safe_details.pop(key, None)
            safe_details.update(_details(details))
            run_id = self.tasks.record_operation(
                owner_id=row["owner_id"], node_id=row["node_id"], action=row["action"], target=row["target"],
                started_at=row["started_at"], ended_at=end, status=status, details=safe_details,
                operation_count=count, context_key=row["context_key"], task_title=row["task_title"],
                operation_id=reservation_id, connection=db,
            )
            self.auth.record_operation(row["owner_id"], status == "success", duration, count,
                                       started_at=row["started_at"], connection=db)
            self.auth.audit(row["owner_id"], row["action"], row["target"],
                            {**safe_details, "reservation_id": reservation_id, "node_id": row["node_id"],
                             "status": status, "duration_ms": round(duration * 1000), "operation_count": count},
                            created_at=end, connection=db)
            db.execute("""UPDATE operation_reservations SET status='settled',settled_at=?,outcome=?,
                       operation_count=?,task_run_id=?,details=? WHERE id=?""",
                       (end, status, count, run_id, json.dumps(safe_details, ensure_ascii=False), reservation_id))
            return run_id

    def retain_unconfirmed(self, reservation_id: str, **metadata: Any) -> None:
        """Best-effort annotation without replacing the original RPC outcome.

        If storage is unavailable, the durable pending minimum still counts and
        its deadline supplies the unconfirmed label after storage recovers.
        """
        try:
            self.mark_unconfirmed(reservation_id, **metadata)
        except Exception:
            logging.getLogger("lucas.gateway").error("Operation requires accounting review: %s", reservation_id)

    def complete(self, reservation_id: str, **completion: Any) -> None:
        """Keep a confirmed remote result intact if local settlement fails."""
        try:
            self.settle(reservation_id, **completion)
        except Exception:
            self.retain_unconfirmed(reservation_id, error_type="AccountingError",
                                    reason="accounting_failed", confirmed_outcome=completion.get("status", "success"))
            logging.getLogger("lucas.gateway").error("Confirmed operation could not be settled: %s", reservation_id)
