"""Real SQLite admission/settlement regressions; no Node, browser or live actions."""
from __future__ import annotations

import calendar
import json
import multiprocessing
import sqlite3
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from gpt_windows_connector import operation_admission
from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector.entitlements import ensure_request_capacity, snapshot
from gpt_windows_connector.operation_admission import OperationAdmissionStore, list_unresolved
from gpt_windows_connector.task_runs import TaskRunStore

OCT = float(calendar.timegm((2026, 10, 15, 12, 0, 0)))
NOV = float(calendar.timegm((2026, 11, 1, 0, 0, 1)))


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("LUCAS_BETA_FREE", "1")
    monkeypatch.setattr(operation_admission, "time", SimpleNamespace(time=lambda: OCT))
    path = tmp_path / "operations.db"
    auth = AuthStore(path, "synthetic-operation-test-secret")
    tasks = TaskRunStore(path)
    store = OperationAdmissionStore(path, auth_store=auth, task_store=tasks)
    return SimpleNamespace(path=path, auth=auth, tasks=tasks, store=store)


def reserve(ledger, **overrides):
    kwargs = dict(owner_id="owner", node_id="node", action="shell.run", target="workspace")
    kwargs.update(overrides)
    return ledger.store.reserve(**kwargs)


def scalar(path, sql, params=()):
    with sqlite3.connect(path) as db:
        return db.execute(sql, params).fetchone()[0]


def test_pending_unknown_and_completed_are_disjoint(ledger):
    first = reserve(ledger, requested_operations=3)
    second = reserve(ledger, requested_operations=2)
    assert (snapshot(ledger.path, "owner", OCT).requests_used, snapshot(ledger.path, "owner", OCT).requests_pending) == (0, 5)
    ledger.store.mark_unconfirmed(first["id"], error_type="TimeoutError")
    ent = snapshot(ledger.path, "owner", OCT)
    assert (ent.requests_used, ent.requests_pending, ent.requests_unconfirmed) == (0, 2, 3)
    assert ent.as_dict()["request_remaining"] == 99995
    ledger.store.settle(first["id"], operation_count=8, ended_at=OCT + 5)
    ledger.store.settle(second["id"], status="failed", operation_count=2, ended_at=OCT + 6)
    ent = snapshot(ledger.path, "owner", OCT + 6)
    assert (ent.requests_used, ent.requests_pending, ent.requests_unconfirmed) == (10, 0, 0)
    assert list_unresolved(ledger.path, "owner", now=OCT + 6) == []
    assert scalar(ledger.path, "SELECT COUNT(*) FROM task_steps") == 2
    assert scalar(ledger.path, "SELECT SUM(success_count) FROM task_runs") == 1
    assert scalar(ledger.path, "SELECT SUM(error_count) FROM task_runs") == 1
    assert scalar(ledger.path, "SELECT operation_count FROM usage_daily") == 10
    assert "error_type" not in json.loads(scalar(ledger.path, "SELECT details FROM task_steps WHERE id=?", (first["id"],)))


def test_deadline_is_not_a_refund_and_survives_restart(ledger):
    item = reserve(ledger, requested_operations=100000, timeout_seconds=10)
    reopened = OperationAdmissionStore(ledger.path, auth_store=ledger.auth, task_store=ledger.tasks)
    ent = snapshot(ledger.path, "owner", OCT + 11)
    assert (ent.requests_used, ent.requests_pending, ent.requests_unconfirmed) == (0, 0, 100000)
    assert ent.as_dict()["request_remaining"] == 0
    with pytest.raises(PermissionError):
        ensure_request_capacity(ledger.path, "owner", now=OCT + 1000)
    assert scalar(ledger.path, "SELECT status FROM operation_reservations") == "outcome_unconfirmed"
    assert scalar(ledger.path, "SELECT COUNT(*) FROM audit_logs WHERE action='operation.outcome_unconfirmed'") == 1
    assert list_unresolved(ledger.path, "owner", now=OCT + 1000)[0]["id"] == item["id"]
    reopened.settle(item["id"], operation_count=100005, ended_at=OCT + 2000)
    assert snapshot(ledger.path, "owner", OCT + 2000).requests_used == 100005


def test_rollover_releases_only_period_hold_and_late_completion_uses_admission_time(ledger, monkeypatch):
    old = reserve(ledger, requested_operations=13)
    ledger.store.mark_unconfirmed(old["id"], error_type="TimeoutError")
    monkeypatch.setattr(operation_admission, "time", SimpleNamespace(time=lambda: NOV))
    current = reserve(ledger, requested_operations=2)
    ent = snapshot(ledger.path, "owner", NOV)
    assert (ent.requests_used, ent.requests_pending, ent.requests_unconfirmed) == (0, 2, 0)
    unresolved = list_unresolved(ledger.path, "owner", now=NOV)
    assert {item["id"]: item["currently_held"] for item in unresolved} == {old["id"]: False, current["id"]: True}
    ledger.store.settle(old["id"], operation_count=19, ended_at=NOV + 1)
    assert snapshot(ledger.path, "owner", NOV + 1).requests_used == 0
    assert snapshot(ledger.path, "owner", OCT + 1).requests_used == 19
    assert scalar(ledger.path, "SELECT started_at FROM task_steps WHERE id=?", (old["id"],)) == OCT
    assert scalar(ledger.path, "SELECT day FROM usage_daily") == "2026-10-15"


def test_first_completion_is_immutable_and_idempotent(ledger):
    item = reserve(ledger)
    run = ledger.store.settle(item["id"], operation_count=7, ended_at=OCT + 2, details={"sub_operations": ["private-command"] * 7})
    with sqlite3.connect(ledger.path) as db:
        before = {table: db.execute(f"SELECT * FROM {table}").fetchall() for table in ("task_steps", "task_runs", "usage_daily", "audit_logs", "operation_reservations")}
    assert ledger.store.settle(item["id"], status="failed", operation_count=999, ended_at=NOV, details={"error_type": "WrongOutcome"}) == run
    ledger.store.mark_unconfirmed(item["id"], error_type="TimeoutError")
    with sqlite3.connect(ledger.path) as db:
        assert before == {table: db.execute(f"SELECT * FROM {table}").fetchall() for table in before}
    assert scalar(ledger.path, "SELECT id FROM task_steps") == item["id"]


@pytest.mark.parametrize("failure", ["task_runs", "task_steps", "usage_daily", "audit_logs", "tombstone"])
def test_settlement_rolls_back_every_side_effect(ledger, failure):
    item = reserve(ledger)
    with sqlite3.connect(ledger.path) as db:
        if failure == "tombstone":
            db.execute("CREATE TRIGGER reject_settlement BEFORE UPDATE ON operation_reservations WHEN NEW.status='settled' BEGIN SELECT RAISE(ABORT,'synthetic atomicity failure'); END")
        else:
            db.execute(f"CREATE TRIGGER reject_settlement BEFORE INSERT ON {failure} BEGIN SELECT RAISE(ABORT,'synthetic atomicity failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="synthetic atomicity failure"):
        ledger.store.settle(item["id"], operation_count=9, ended_at=OCT + 1)
    for table in ("task_runs", "task_steps", "usage_daily"):
        assert scalar(ledger.path, f"SELECT COUNT(*) FROM {table}") == 0
    assert scalar(ledger.path, "SELECT COUNT(*) FROM audit_logs") == 1
    assert scalar(ledger.path, "SELECT status FROM operation_reservations") == "pending"
    assert snapshot(ledger.path, "owner", OCT).requests_pending == 1
    with sqlite3.connect(ledger.path) as db:
        db.execute("DROP TRIGGER reject_settlement")
    ledger.store.settle(item["id"], operation_count=9, ended_at=OCT + 1)
    assert snapshot(ledger.path, "owner", OCT).requests_used == 9


def test_expired_unknown_can_gain_known_remote_outcome_after_accounting_failure(ledger):
    item = reserve(ledger, timeout_seconds=1)
    snapshot(ledger.path, "owner", OCT + 2)
    with sqlite3.connect(ledger.path) as db:
        db.execute("CREATE TRIGGER reject_settlement BEFORE INSERT ON task_steps BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    ledger.store.complete(item["id"], status="success", operation_count=6)
    entry = list_unresolved(ledger.path, "owner", now=OCT + 3)[0]
    assert entry["status"] == "outcome_unconfirmed"
    assert entry["reserved_operations"] == 1
    assert entry["details"] == {"reason": "accounting_failed", "error_type": "AccountingError", "confirmed_outcome": "success"}
    ledger.store.complete(item["id"], status="success", operation_count=6)
    assert scalar(ledger.path, "SELECT COUNT(*) FROM audit_logs WHERE action='operation.accounting_unconfirmed'") == 1


def test_sanitized_metadata_never_stores_payload_or_error_strings(ledger):
    metadata = {"source": "oauth", "agent": "client", "session_id": "session", "task_title": "Safe title",
                "command": "private-command --token private-token", "stdout": "private-output", "error": "private-exception",
                "headers": {"Authorization": "private-token"}, "sub_operations": ["private-command", "private-argument"]}
    item = reserve(ledger, details=metadata, task_title="Safe title")
    ledger.store.settle(item["id"], operation_count=2, details=metadata)
    with sqlite3.connect(ledger.path) as db:
        serialized = str({table: db.execute(f"SELECT * FROM {table}").fetchall() for table in ("operation_reservations", "task_steps", "audit_logs")})
    for secret in ("private-command", "private-token", "private-output", "private-exception", "private-argument"):
        assert secret not in serialized
    details = json.loads(scalar(ledger.path, "SELECT details FROM task_steps"))
    assert details["sub_operations"] == ["shell.run", "shell.run"]
    assert metadata["sub_operations"] == ["private-command", "private-argument"]


def test_unresolved_owner_and_filters_precede_limit(ledger, monkeypatch):
    keep = reserve(ledger, node_id="wanted")
    for index in range(3):
        monkeypatch.setattr(operation_admission, "time", SimpleNamespace(time=lambda index=index: OCT + index + 1))
        reserve(ledger, node_id="other")
    reserve(ledger, owner_id="different-owner", node_id="wanted")
    result = list_unresolved(ledger.path, "owner", now=OCT + 10, limit=1, node_id="wanted", since=OCT)
    assert [item["id"] for item in result] == [keep["id"]]
    assert list_unresolved(ledger.path, "owner", now=OCT + 10, node_id="wanted", since=OCT + 1) == []


def test_legacy_schema_has_zero_reservations_and_legacy_steps_still_count(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.executescript("CREATE TABLE subscriptions(user_id TEXT,plan TEXT,status TEXT); CREATE TABLE task_steps(owner_id TEXT,started_at REAL); INSERT INTO task_steps VALUES('owner',1792065600);")
    # The old schema has no operation_count, overrides, bindings or reservation table.
    ent = snapshot(path, "owner", OCT)
    assert (ent.requests_used, ent.requests_pending, ent.requests_unconfirmed) == (1, 0, 0)
    assert list_unresolved(path, "owner", now=OCT) == []


def test_paid_expansion_admin_bonus_and_expiry_rules_remain(ledger, monkeypatch):
    monkeypatch.setenv("LUCAS_BETA_FREE", "0")
    with sqlite3.connect(ledger.path) as db:
        for column, kind in (("expansion_quantity", "INTEGER DEFAULT 0"), ("current_period_start", "REAL"), ("current_period_end", "REAL"), ("bonus_requests", "INTEGER DEFAULT 0")):
            db.execute(f"ALTER TABLE subscriptions ADD COLUMN {column} {kind}")
        db.execute("INSERT INTO subscriptions(user_id,plan,status,updated_at,expansion_quantity,current_period_start,current_period_end,bonus_requests) VALUES('owner','pro_plus','active',?,2,?,?,4)", (OCT, OCT - 100, OCT + 1000))
    first = reserve(ledger, requested_operations=300004)
    assert first["period_start"] == OCT - 100
    assert snapshot(ledger.path, "owner", OCT).as_dict()["request_remaining"] == 0
    with pytest.raises(PermissionError):
        reserve(ledger)
    with sqlite3.connect(ledger.path) as db:
        db.execute("INSERT INTO entitlement_overrides(user_id,bonus_requests,expires_at) VALUES('owner',2,?)", (OCT + 5,))
    reserve(ledger, requested_operations=2)
    assert snapshot(ledger.path, "owner", OCT + 6).request_limit == 300004
    # Beta ignores historical paid periods and expands only by the existing bonuses.
    monkeypatch.setenv("LUCAS_BETA_FREE", "1")
    assert snapshot(ledger.path, "owner", OCT).request_limit == 100006
    assert snapshot(ledger.path, "owner", NOV).requests_pending == 0


def test_caller_owned_helpers_do_not_commit_or_close(ledger):
    db = sqlite3.connect(ledger.path)
    db.row_factory = sqlite3.Row
    db.execute("BEGIN IMMEDIATE")
    ledger.auth.record_operation("owner", True, 2.0, 3, connection=db, started_at=OCT)
    ledger.auth.audit("owner", "test", details={"safe": True}, connection=db)
    run = ledger.tasks.record_operation(owner_id="owner", node_id="node", action="test", target="workspace",
        started_at=OCT, ended_at=OCT + 2, status="success", operation_count=3, operation_id="stable-test-id", connection=db)
    assert ledger.tasks.record_operation(owner_id="owner", node_id="node", action="test", target="workspace",
        started_at=OCT, ended_at=OCT + 2, status="success", operation_count=99, operation_id="stable-test-id", connection=db) == run
    assert snapshot(ledger.path, "owner", OCT, connection=db).requests_used == 3
    assert db.in_transaction
    db.rollback()
    assert db.execute("SELECT COUNT(*) FROM task_steps").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM usage_daily").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == 0
    db.close()


def _reserve_process(path, ready, release, outcomes):
    # Separate interpreters and SQLite connections, not a process-local lock.
    auth = AuthStore(path, "synthetic-process-secret")
    tasks = TaskRunStore(path)
    operation_admission.time = SimpleNamespace(time=lambda: OCT)
    store = OperationAdmissionStore(path, auth_store=auth, task_store=tasks)
    ready.put(True)
    release.wait(15)
    try:
        item = store.reserve(owner_id="owner", node_id="node", action="workspace.info", target="workspace")
        outcomes.put(("admitted", item["id"]))
    except PermissionError:
        outcomes.put(("denied", None))


def test_cross_process_last_slot_is_reserved_once(ledger):
    ledger.tasks.record_operation(owner_id="owner", node_id="node", action="prior", target="workspace", started_at=OCT - 1,
                                  ended_at=OCT, status="success", operation_count=99999)
    ctx = multiprocessing.get_context("spawn")
    ready, outcomes, release = ctx.Queue(), ctx.Queue(), ctx.Event()
    processes = [ctx.Process(target=_reserve_process, args=(ledger.path, ready, release, outcomes)) for _ in range(2)]
    try:
        for process in processes:
            process.start()
        for _ in processes:
            assert ready.get(timeout=20)
        release.set()
        results = [outcomes.get(timeout=20)[0] for _ in processes]
        assert sorted(results) == ["admitted", "denied"]
        for process in processes:
            process.join(20)
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(5)
    ent = snapshot(ledger.path, "owner", OCT)
    assert (ent.requests_used, ent.requests_pending, ent.as_dict()["request_remaining"]) == (99999, 1, 0)


def test_writer_wait_captures_new_period_after_lock(ledger, monkeypatch):
    clock = [NOV - 2]
    monkeypatch.setattr(operation_admission, "time", SimpleNamespace(time=lambda: clock[0]))
    entered = threading.Event()
    original_transaction = operation_admission._transaction

    @contextmanager
    def observed_transaction(path):
        entered.set()
        with original_transaction(path) as db:
            yield db

    monkeypatch.setattr(operation_admission, "_transaction", observed_transaction)
    locked = sqlite3.connect(ledger.path)
    locked.execute("BEGIN IMMEDIATE")
    result = []
    errors = []

    def writer():
        try:
            result.append(reserve(ledger))
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=writer)
    thread.start()
    assert entered.wait(5)
    clock[0] = NOV
    locked.commit()
    locked.close()
    thread.join(5)
    assert not thread.is_alive() and not errors
    assert result[0]["started_at"] == NOV
    assert result[0]["period_start"] == NOV - 1


def test_snapshot_never_observes_partial_settlement(ledger, monkeypatch):
    item = reserve(ledger)
    inserted, release, read_done = threading.Event(), threading.Event(), threading.Event()
    original = ledger.tasks.record_operation

    def delayed_record(**kwargs):
        result = original(**kwargs)
        inserted.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(ledger.tasks, "record_operation", delayed_record)
    outcomes, errors = [], []

    def settle():
        try:
            ledger.store.settle(item["id"], operation_count=1)
        except BaseException as exc:
            errors.append(exc)

    def read():
        try:
            outcomes.append(snapshot(ledger.path, "owner", OCT))
        except BaseException as exc:
            errors.append(exc)
        finally:
            read_done.set()

    writer = threading.Thread(target=settle)
    writer.start()
    assert inserted.wait(5)
    reader = threading.Thread(target=read)
    reader.start()
    assert not read_done.wait(0.05)
    release.set()
    writer.join(5)
    reader.join(5)
    assert not errors and not writer.is_alive() and not reader.is_alive()
    ent = outcomes[0]
    assert (ent.requests_used, ent.requests_pending, ent.requests_unconfirmed) == (1, 0, 0)


def test_paid_period_changes_share_completed_and_unresolved_timestamp_rule(ledger, monkeypatch):
    monkeypatch.setenv("LUCAS_BETA_FREE", "0")
    with sqlite3.connect(ledger.path) as db:
        db.execute("ALTER TABLE subscriptions ADD COLUMN current_period_start REAL")
        db.execute("ALTER TABLE subscriptions ADD COLUMN current_period_end REAL")
        db.execute("INSERT INTO subscriptions(user_id,plan,status,updated_at,current_period_start,current_period_end) VALUES('owner','pro','active',?,?,?)", (OCT, OCT - 100, OCT + 10))
    pending = reserve(ledger, requested_operations=3)
    unknown = reserve(ledger, requested_operations=4)
    ledger.store.mark_unconfirmed(unknown["id"], error_type="TimeoutError")
    # A paid plan change moves the window; admission remains inside its overlap.
    with sqlite3.connect(ledger.path) as db:
        db.execute("UPDATE subscriptions SET current_period_start=?,current_period_end=?", (OCT - 1, OCT + 1000))
    ent = snapshot(ledger.path, "owner", OCT + 20)
    assert (ent.requests_used, ent.requests_pending, ent.requests_unconfirmed) == (0, 3, 4)
    unresolved = list_unresolved(ledger.path, "owner", now=OCT + 20)
    assert all(item["currently_held"] for item in unresolved)
    assert all(item["period_end"] == OCT + 10 for item in unresolved)
    ledger.store.settle(pending["id"], operation_count=3, ended_at=OCT + 21)
    ent = snapshot(ledger.path, "owner", OCT + 21)
    assert (ent.requests_used, ent.requests_pending, ent.requests_unconfirmed) == (3, 0, 4)
    # A non-overlapping renewal excludes both the completed step and old hold.
    with sqlite3.connect(ledger.path) as db:
        db.execute("UPDATE subscriptions SET current_period_start=?,current_period_end=?", (OCT + 30, OCT + 2000))
    ent = snapshot(ledger.path, "owner", OCT + 31)
    assert (ent.requests_used, ent.requests_pending, ent.requests_unconfirmed) == (0, 0, 0)
    assert list_unresolved(ledger.path, "owner", now=OCT + 31)[0]["currently_held"] is False
    ledger.store.settle(unknown["id"], operation_count=6, ended_at=OCT + 32)
    assert snapshot(ledger.path, "owner", OCT + 32).requests_used == 0


@pytest.mark.parametrize("metadata", [None, "private-value", {"source": [], "confirmed_outcome": {}, "agent": [], "session_id": {}, "sub_operations": "private-command"}])
def test_malformed_metadata_is_sanitized_without_blocking_accounting(ledger, metadata):
    item = reserve(ledger, details=metadata)
    ledger.store.settle(item["id"], details=metadata)
    assert scalar(ledger.path, "SELECT operation_count FROM task_steps") == 1
    assert "private" not in scalar(ledger.path, "SELECT details FROM task_steps")


def test_admin_reservations_keep_admin_and_expiring_bonus_limits(ledger, monkeypatch):
    monkeypatch.setenv("LUCAS_BETA_FREE", "0")
    with sqlite3.connect(ledger.path) as db:
        db.execute("INSERT INTO users(id,email,provider,created_at,updated_at,role) VALUES('owner','admin@example.invalid','test',?,?,'admin')", (OCT, OCT))
    ent = snapshot(ledger.path, "owner", OCT)
    assert ent.admin_grant and ent.plan == "pro_plus" and ent.request_limit == 100000
    reserve(ledger, requested_operations=100000)
    with sqlite3.connect(ledger.path) as db:
        db.execute("INSERT INTO entitlement_overrides(user_id,bonus_requests,expires_at) VALUES('owner',2,?)", (OCT + 5,))
    reserve(ledger, requested_operations=2)
    with pytest.raises(PermissionError):
        reserve(ledger)
    ent = snapshot(ledger.path, "owner", OCT + 6)
    assert (ent.requests_pending, ent.request_limit, ent.as_dict()["request_remaining"]) == (100002, 100000, 0)
    monkeypatch.setenv("LUCAS_BETA_FREE", "1")
    ent = snapshot(ledger.path, "owner", OCT + 6)
    assert ent.admin_grant and ent.plan == "free" and ent.request_limit == 100000


def test_late_record_uses_existing_task_group_without_recounting(ledger):
    common = dict(owner_id="owner", node_id="node", action="workspace.info", target="workspace", context_key="workspace")
    run_id = ledger.tasks.record_operation(**common, started_at=OCT - 3, ended_at=OCT - 2, status="success")
    item = reserve(ledger, context_key="workspace", task_title="Current task")
    assert ledger.store.settle(item["id"], status="failed", operation_count=2, ended_at=OCT + 1) == run_id
    assert scalar(ledger.path, "SELECT COUNT(*) FROM task_runs") == 1
    assert scalar(ledger.path, "SELECT success_count FROM task_runs") == 1
    assert scalar(ledger.path, "SELECT error_count FROM task_runs") == 1
    assert scalar(ledger.path, "SELECT title FROM task_runs") == "Current task"
