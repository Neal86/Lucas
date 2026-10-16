"""Task history accuracy through real SQLite and authenticated local HTTP.

Only disposable accounts/stores and synthetic operation records are used. No
Node, browser, provider, deployment, or external operation is contacted.
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from gpt_windows_connector import operation_admission, task_runs
from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector.entitlements import snapshot
from gpt_windows_connector.operation_admission import OperationAdmissionStore
from gpt_windows_connector.task_runs import TaskRunStore

NOW = 1_792_065_600.0  # A fixed UTC October 2026 instant.


def record(store, **changes):
    args = dict(owner_id="owner", node_id="selected", action="fixture.operation",
                target="fixture-only", context_key="fixture-context", task_title="Fixture task",
                started_at=NOW + 10, ended_at=NOW + 20, status="success")
    args.update(changes)
    return store.record_operation(**args)


def stored_rows(path):
    with sqlite3.connect(path) as db:
        return {name: db.execute(f"SELECT * FROM {name} ORDER BY id").fetchall()
                for name in ("task_runs", "task_steps")}


def test_reverse_completion_keeps_earliest_admission_and_actual_span(tmp_path, monkeypatch):
    path = tmp_path / "admission.sqlite3"
    auth = AuthStore(path, "synthetic-task-history-secret" * 2)
    tasks = TaskRunStore(path)
    admission = OperationAdmissionStore(path, auth_store=auth, task_store=tasks)
    clock = SimpleNamespace(value=NOW)
    monkeypatch.setenv("LUCAS_BETA_FREE", "1")
    monkeypatch.setattr(operation_admission, "time", SimpleNamespace(time=lambda: clock.value))
    monkeypatch.setattr(task_runs, "time", SimpleNamespace(time=lambda: clock.value))
    common = dict(owner_id="owner", node_id="selected", action="fixture.operation",
                  target="fixture-only", context_key="fixture-context", task_title="Fixture task")
    slow = admission.reserve(**common)
    clock.value = NOW + 10
    fast = admission.reserve(**common)
    clock.value = NOW + 20
    run_id = admission.settle(fast["id"], operation_count=2)
    clock.value = NOW + 100
    assert admission.settle(slow["id"], operation_count=3) == run_id
    clock.value = NOW + 500
    runs = tasks.list_runs("owner")
    assert len(runs) == 1
    run = runs[0]
    assert run["started_at"] == min(step["started_at"] for step in run["steps"]) == NOW
    assert run["ended_at"] == run["last_activity_at"] == NOW + 100
    assert run["duration_ms"] == 100_000
    assert (run["success_count"], run["error_count"], run["status"]) == (2, 0, "completed")
    assert [step["operation_count"] for step in run["steps"]] == [3, 2]
    ent = snapshot(path, "owner", clock.value)
    assert (ent.requests_used, ent.requests_pending, ent.requests_unconfirmed) == (5, 0, 0)
    before = stored_rows(path)
    assert admission.settle(slow["id"], operation_count=999, status="failed") == run_id
    assert stored_rows(path) == before
    assert snapshot(path, "owner", clock.value).requests_used == 5


def test_late_earlier_completion_cannot_shrink_span_or_make_task_idle(tmp_path, monkeypatch):
    tasks = TaskRunStore(tmp_path / "late.sqlite3")
    current = record(tasks, started_at=NOW + 20, ended_at=NOW + 100)
    assert record(tasks, started_at=NOW, ended_at=NOW + 40, status="failed") == current
    monkeypatch.setattr(task_runs, "time", SimpleNamespace(time=lambda: NOW + 350))
    run = tasks.list_runs("owner")[0]
    assert (run["started_at"], run["last_activity_at"], run["ended_at"]) == (NOW, NOW + 100, NOW + 100)
    assert (run["status"], run["duration_ms"]) == ("running", 350_000)
    assert (run["success_count"], run["error_count"]) == (1, 1)
    monkeypatch.setattr(task_runs, "time", SimpleNamespace(time=lambda: NOW + 500))
    assert tasks.list_runs("owner")[0]["duration_ms"] == 100_000


def test_boundary_update_obeys_caller_transaction_and_operation_id_replay(tmp_path):
    path = tmp_path / "transaction.sqlite3"
    tasks = TaskRunStore(path)
    run_id = record(tasks, operation_id="first")
    before = stored_rows(path)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN IMMEDIATE")
        assert record(tasks, started_at=NOW, ended_at=NOW + 100,
                      operation_id="second", connection=db) == run_id
        row = db.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
        assert (row["started_at"], row["ended_at"], row["success_count"]) == (NOW, NOW + 100, 2)
        assert record(tasks, started_at=NOW - 1000, ended_at=NOW + 1000,
                      operation_id="second", status="failed", connection=db) == run_id
        assert tuple(db.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()) == tuple(row)
        assert db.in_transaction
        db.rollback()
        assert stored_rows(path) == before
        assert db.execute("SELECT COUNT(*) FROM task_steps").fetchone()[0] == 1
    finally:
        db.close()


def test_nullable_legacy_end_uses_existing_activity_without_backfilling_on_read(tmp_path, monkeypatch):
    path = tmp_path / "legacy.sqlite3"
    tasks = TaskRunStore(path)
    first = record(tasks, started_at=NOW + 50, ended_at=NOW + 100)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE task_runs SET ended_at=NULL WHERE id=?", (first,))
    before = stored_rows(path)
    monkeypatch.setattr(task_runs, "time", SimpleNamespace(time=lambda: NOW + 500))
    assert tasks.list_runs("owner")[0]["duration_ms"] == 50_000
    assert stored_rows(path) == before
    assert record(tasks, started_at=NOW, ended_at=NOW + 20) == first
    run = tasks.list_runs("owner")[0]
    assert (run["started_at"], run["last_activity_at"], run["ended_at"], run["duration_ms"]) == (
        NOW, NOW + 100, NOW + 100, 100_000)


@pytest.mark.parametrize("changes", [
    {"owner_id": "other-owner"}, {"node_id": "other-computer"},
    {"context_key": "other-context"}, {"task_title": "Other task"},
    {"started_at": NOW + 400, "ended_at": NOW + 401},
])
def test_existing_owner_node_context_title_and_idle_group_boundaries_remain(tmp_path, changes):
    tasks = TaskRunStore(tmp_path / "groups.sqlite3")
    first = record(tasks)
    assert record(tasks, **changes) != first


def test_fallback_title_upgrade_and_exact_idle_boundary_remain(tmp_path):
    tasks = TaskRunStore(tmp_path / "title.sqlite3")
    first = record(tasks, task_title=None)
    assert record(tasks, started_at=NOW + 30, ended_at=NOW + 320) == first
    run = tasks.list_runs("owner")[0]
    assert (run["title"], run["context_key"]) == ("Fixture task", "fixture-context::task::Fixture task")
    assert (run["started_at"], run["ended_at"]) == (NOW + 10, NOW + 320)


@pytest.fixture
def history_api(tmp_path, monkeypatch):
    from gpt_windows_connector import gateway, webapp

    path = tmp_path / "history-api.sqlite3"
    auth = AuthStore(path, "synthetic-history-api-secret" * 2)
    owner = auth.register("history-owner@example.invalid", "synthetic-history-password")
    other = auth.register("history-other@example.invalid", "synthetic-history-password")
    tasks = TaskRunStore(path)
    for name, value in {"db_path": path, "auth": auth, "task_runs": tasks}.items():
        monkeypatch.setattr(gateway, name, value)
    monkeypatch.setattr(webapp, "time", SimpleNamespace(time=lambda: NOW))
    # Multiple nodes, owners, periods and runs expose scope errors hidden by a
    # fixture that has only one completed computer. Counts are weighted units.
    seeds = [
        (owner, "selected", "recent-a", NOW - 120, 3, 2),
        (owner, "selected", "recent-b", NOW - 90, 7, 5),
        (owner, "other", "other-node", NOW - 60, 11, 7),
        (other, "selected", "foreign-owner", NOW - 30, 20, 99),
        (owner, "selected", "older", NOW - 40 * 86400, 13, 11),
        (owner, "node' OR 1=1 --", "literal-id", NOW - 20, 17, 13),
    ]
    for user, node, context, start, duration, units in seeds:
        record(tasks, owner_id=user.id, node_id=node, context_key=context,
               started_at=start, ended_at=start + duration, operation_count=units)
    client = TestClient(Starlette(routes=[Route("/api/task-runs", webapp.api_task_runs)]))
    with client:
        yield SimpleNamespace(client=client, path=path, tasks=tasks, owner=owner, other=other,
                              headers={"Authorization": "Bearer " + auth.issue_token(owner)},
                              other_headers={"Authorization": "Bearer " + auth.issue_token(other)})


@pytest.mark.parametrize("node,days,expected", [
    ("selected", "all", (3, 18, 23_000)),
    ("selected", "7", (2, 7, 10_000)),
    ("selected", "30", (2, 7, 10_000)),
    ("selected", "90", (3, 18, 23_000)),
    ("other", "7", (1, 7, 11_000)),
    ("absent", "all", (0, 0, 0)),
    ("  selected  ", "7", (2, 7, 10_000)),
    ("node' OR 1=1 --", "7", (1, 13, 17_000)),
    (None, "7", (4, 27, 38_000)),
    ("", "all", (5, 38, 51_000)),
])
def test_http_summary_matches_owner_computer_and_period(history_api, node, days, expected):
    x = history_api
    params = {"days": days, "owner_id": x.other.id}
    if node is not None:
        params["node_id"] = node
    response = x.client.get("/api/task-runs", params=params, headers=x.headers)
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"runs", "summary", "unresolved_operations"}
    assert data["unresolved_operations"] == []
    summary = data["summary"]
    assert (summary["task_runs"], summary["operations"], summary["duration_ms"]) == expected
    assert summary["days"] == (None if days == "all" else int(days))
    assert len(data["runs"]) == expected[0]
    assert sum(step["operation_count"] for run in data["runs"] for step in run["steps"]) == expected[1]
    assert all(run["owner_id"] == x.owner.id for run in data["runs"])
    if node and node.strip():
        assert all(run["node_id"] == node.strip() for run in data["runs"])


def test_summary_is_not_limited_to_the_visible_page_or_another_owner(history_api):
    x = history_api
    response = x.client.get("/api/task-runs?node_id=selected&days=7&limit=1", headers=x.headers)
    data = response.json()
    assert response.status_code == 200 and len(data["runs"]) == 1
    assert data["summary"] == {"task_runs": 2, "operations": 7, "duration_ms": 10_000, "days": 7}
    other = x.client.get("/api/task-runs?node_id=selected&days=7", headers=x.other_headers).json()
    assert other["summary"] == {"task_runs": 1, "operations": 99, "duration_ms": 20_000, "days": 7}


def test_period_start_is_inclusive_without_changing_run_and_step_attribution(history_api):
    x = history_api
    cutoff = NOW - 7 * 86400
    record(x.tasks, owner_id=x.owner.id, context_key="at-cutoff", started_at=cutoff,
           ended_at=cutoff + 2, operation_count=3)
    record(x.tasks, owner_id=x.owner.id, context_key="before-cutoff", started_at=cutoff - 1,
           ended_at=cutoff + 2, operation_count=50)
    before = stored_rows(x.path)
    data = x.client.get("/api/task-runs?node_id=selected&days=7", headers=x.headers).json()
    assert data["summary"] == {"task_runs": 3, "operations": 10, "duration_ms": 12_000, "days": 7}
    assert len(data["runs"]) == 3
    assert stored_rows(x.path) == before
