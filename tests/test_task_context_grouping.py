"""Literal task-context grouping using real SQLite/admission and local HTTP.

All accounts, records and clocks are disposable fixtures. No Node, provider or
external operation is used; billing totals are read, not externally mutated.
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from gpt_windows_connector import operation_admission
from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector.entitlements import snapshot
from gpt_windows_connector.operation_admission import OperationAdmissionStore
from gpt_windows_connector.task_runs import TaskRunStore

NOW = 1_792_065_600.0
COLLISIONS = [
    ("synthetic_workspace", "syntheticXworkspace"),
    ("synthetic%workspace", "syntheticXYZworkspace"),
    ("100%", "100"),
    ("work__name", "workXYname"),
    ("work!_%", "work!AX"),
    (r"C:\Work\project_a%", r"C:\Work\projectXa123"),
    ("工作_%", "工作甲乙"),
    ("team'_%", "team'XX"),
]


def record(tasks, context, *, title=None, start=NOW, end=None, **changes):
    args = dict(owner_id="owner", node_id="computer", action="fixture.operation",
                target="fixture-only", context_key=context, task_title=title,
                started_at=start, ended_at=start + 1 if end is None else end,
                status="success", operation_count=1)
    args.update(changes)
    return tasks.record_operation(**args)


def all_rows(path):
    with sqlite3.connect(path) as db:
        return {name: db.execute(f"SELECT * FROM {name} ORDER BY rowid").fetchall()
                for name in ("task_runs", "task_steps", "usage_daily", "audit_logs", "operation_reservations")}


@pytest.mark.parametrize("requested,unrelated", COLLISIONS)
def test_wildcards_in_context_do_not_join_another_titled_context(tmp_path, requested, unrelated):
    tasks = TaskRunStore(tmp_path / "literal.sqlite3")
    other = record(tasks, unrelated, title="Other task")
    current = record(tasks, requested, start=NOW + 2)
    assert current != other
    runs = {run["id"]: run for run in tasks.list_runs("owner")}
    assert set(runs) == {other, current}
    assert runs[other]["context_key"] == unrelated + "::task::Other task"
    assert runs[current]["context_key"] == requested
    assert all(len(run["steps"]) == 1 for run in runs.values())


@pytest.mark.parametrize("context", ["plain", "with_under", "100%literal", "with!escape", "!_%!", r"C:\Work\A_%!", "中文_百分%", "quote'_%", "trailing!", "emoji😀_%"])
def test_same_literal_context_keeps_titled_untitled_and_upgrade_contracts(tmp_path, context):
    tasks = TaskRunStore(tmp_path / "positive.sqlite3")
    first = record(tasks, context)
    assert record(tasks, context, start=NOW + 2) == first
    assert record(tasks, context, title="  First   task  ", start=NOW + 4) == first
    assert record(tasks, context, start=NOW + 6) == first
    run = tasks.list_runs("owner")[0]
    assert (run["context_key"], run["title"]) == (context + "::task::First task", "First task")
    assert len(run["steps"]) == 4 and run["success_count"] == 4


def test_most_recent_real_candidate_wins_instead_of_newer_wildcard_collision(tmp_path):
    tasks = TaskRunStore(tmp_path / "latest.sqlite3")
    old = record(tasks, "work_%", title="Old", start=NOW)
    current = record(tasks, "work_%", title="Current", start=NOW + 2)
    unrelated = record(tasks, "workXY", title="Unrelated", start=NOW + 4)
    assert record(tasks, "work_%", start=NOW + 6) == current
    runs = {run["id"]: run for run in tasks.list_runs("owner")}
    assert [len(runs[key]["steps"]) for key in (old, current, unrelated)] == [1, 2, 1]


@pytest.mark.parametrize("gap,joins", [(300, True), (301, False)])
def test_idle_threshold_is_unchanged_for_literal_titled_match(tmp_path, gap, joins):
    tasks = TaskRunStore(tmp_path / "idle.sqlite3")
    first = record(tasks, "work!_%", title="Task")
    second = record(tasks, "work!_%", start=NOW + gap, end=NOW + 1 + gap)
    assert (second == first) is joins


def test_existing_sqlite_case_matching_and_literal_backslash_are_preserved(tmp_path):
    tasks = TaskRunStore(tmp_path / "case.sqlite3")
    first = record(tasks, r"C:\WORK\Name_%!", title="Task")
    assert record(tasks, r"c:\work\name_%!", start=NOW + 2) == first
    # SQLite LIKE does not fold non-ASCII characters by default. Preserve it.
    unicode_run = record(tasks, "Ärea_%", title="Unicode", start=NOW + 4)
    assert record(tasks, "ärea_%", start=NOW + 6) != unicode_run


@pytest.mark.parametrize("setting,requested,joins", [
    ("OFF", "work_%", True), ("ON", "work_%", False),
    ("ON", "WORK_%", True), ("OFF", "WÖRK_%", False),
])
def test_caller_connection_like_case_policy_is_preserved(tmp_path, setting, requested, joins):
    tasks = TaskRunStore(tmp_path / "case-setting.sqlite3")
    first = record(tasks, "WORK_%", title="Task")
    db = sqlite3.connect(tasks.path)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA case_sensitive_like=" + setting)
        db.execute("BEGIN IMMEDIATE")
        current = record(tasks, requested, start=NOW + 2, connection=db)
        assert (current == first) is joins
        db.rollback()
    finally:
        db.close()


@pytest.mark.parametrize("character", ["!", "_", "%", "界"])
def test_long_context_keeps_valid_join_without_like_pattern_expansion(tmp_path, character):
    tasks = TaskRunStore(tmp_path / "long-context.sqlite3")
    context = character * (25_000 if character != "界" else 16_000)
    first = record(tasks, context, title="Task")
    assert record(tasks, context, start=NOW + 2) == first
    run = tasks.list_runs("owner")[0]
    assert run["context_key"] == context + "::task::Task" and len(run["steps"]) == 2


def test_embedded_nul_is_part_of_context_identity(tmp_path):
    tasks = TaskRunStore(tmp_path / "nul.sqlite3")
    unrelated = record(tasks, "workspace\0X", title="Other task")
    current = record(tasks, "workspace\0Y", start=NOW + 2)
    assert current != unrelated
    assert record(tasks, "workspace\0Y", title="Current task", start=NOW + 4) == current
    assert record(tasks, "workspace\0Y", start=NOW + 6) == current
    assert len(tasks.list_runs("owner")) == 2


@pytest.mark.parametrize("changes", [{"owner_id": "other"}, {"node_id": "other-computer"}])
def test_owner_and_computer_scope_remain_exact(tmp_path, changes):
    tasks = TaskRunStore(tmp_path / "owners.sqlite3")
    first = record(tasks, "work_%", title="Task")
    assert record(tasks, "work_%", start=NOW + 2, **changes) != first


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    from gpt_windows_connector import gateway, webapp

    path = tmp_path / "grouping-api.sqlite3"
    auth = AuthStore(path, "synthetic-task-context-signing-key" * 2)
    owner = auth.register("context-owner@example.invalid", "synthetic-context-password")
    foreign = auth.register("context-foreign@example.invalid", "synthetic-context-password")
    tasks = TaskRunStore(path)
    admission = OperationAdmissionStore(path, auth_store=auth, task_store=tasks)
    clock = SimpleNamespace(value=NOW)
    monkeypatch.setenv("LUCAS_BETA_FREE", "1")
    monkeypatch.setattr(operation_admission, "time", SimpleNamespace(time=lambda: clock.value))
    monkeypatch.setattr(webapp, "time", SimpleNamespace(time=lambda: NOW + 100))
    for name, value in {"db_path": path, "auth": auth, "task_runs": tasks}.items():
        monkeypatch.setattr(gateway, name, value)

    def complete(context, title, units, *, user=None, node="computer"):
        current_user = user or owner
        item = admission.reserve(owner_id=current_user.id, node_id=node, action="fixture.operation",
                                 target="fixture-only", context_key=context, task_title=title)
        clock.value += 1
        run = admission.settle(item["id"], operation_count=units)
        clock.value += 1
        return run, item

    with TestClient(webapp.app) as client:
        yield SimpleNamespace(path=path, auth=auth, owner=owner, foreign=foreign, tasks=tasks,
                              admission=admission, clock=clock, complete=complete, client=client,
                              headers={"Authorization": "Bearer " + auth.issue_token(owner)},
                              foreign_headers={"Authorization": "Bearer " + auth.issue_token(foreign)})


@pytest.mark.parametrize("requested,unrelated", COLLISIONS[:2])
def test_real_admission_and_http_keep_task_identity_and_weighted_usage(ledger, requested, unrelated):
    x = ledger
    other, _ = x.complete(unrelated, "Other task", 2)
    current, item = x.complete(requested, None, 3)
    x.complete(requested, "Foreign task", 99, user=x.foreign)
    x.complete(requested, "Other computer", 11, node="another-computer")
    before = all_rows(x.path)
    assert x.admission.settle(item["id"], operation_count=1000, status="failed") == current
    assert all_rows(x.path) == before
    response = x.client.get("/api/task-runs?node_id=computer&days=7&owner_id=" + x.foreign.id, headers=x.headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["runs"]) == 2
    assert {run["id"] for run in data["runs"]} == {other, current}
    assert all(run["owner_id"] == x.owner.id and run["node_id"] == "computer" for run in data["runs"])
    assert sorted(sum(step["operation_count"] for step in run["steps"]) for run in data["runs"]) == [2, 3]
    assert data["summary"] == {"task_runs": 2, "operations": 5, "duration_ms": 2000, "days": 7}
    assert data["unresolved_operations"] == []
    ent = snapshot(x.path, x.owner.id, x.clock.value)
    assert (ent.request_limit, ent.requests_used, ent.requests_pending, ent.requests_unconfirmed) == (100000, 16, 0, 0)
    foreign_data = x.client.get("/api/task-runs?node_id=computer", headers=x.foreign_headers).json()
    assert len(foreign_data["runs"]) == 1 and foreign_data["summary"]["operations"] == 99
    assert all_rows(x.path) == before


def test_failed_settlement_rolls_back_then_retries_into_literal_context_once(ledger):
    x = ledger
    unrelated, _ = x.complete("workX", "Other task", 2)
    item = x.admission.reserve(owner_id=x.owner.id, node_id="computer", action="fixture.operation",
                               target="fixture-only", context_key="work_")
    before = all_rows(x.path)
    with sqlite3.connect(x.path) as db:
        db.execute("CREATE TRIGGER reject_step BEFORE INSERT ON task_steps BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="fixture failure"):
        x.admission.settle(item["id"], operation_count=3)
    assert all_rows(x.path) == before
    with sqlite3.connect(x.path) as db:
        db.execute("DROP TRIGGER reject_step")
    x.clock.value += 1
    current = x.admission.settle(item["id"], operation_count=3)
    assert current != unrelated
    after = all_rows(x.path)
    assert x.admission.settle(item["id"], operation_count=300) == current
    assert all_rows(x.path) == after
    assert snapshot(x.path, x.owner.id, x.clock.value).requests_used == 5


@pytest.mark.parametrize("kind", ["long", "nul"])
def test_long_and_nul_context_settlement_survives_authenticated_http(ledger, kind):
    x = ledger
    context = "!_%" * 10_000 if kind == "long" else "work\0_%"
    first, _ = x.complete(context, "Task", 2)
    second, item = x.complete(context, None, 3)
    assert first == second
    response = x.client.get("/api/task-runs?node_id=computer", headers=x.headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["runs"]) == 1
    assert data["runs"][0]["context_key"] == context + "::task::Task"
    assert len(data["runs"][0]["steps"]) == 2
    assert data["summary"] == {"task_runs": 1, "operations": 5, "duration_ms": 2000, "days": None}
    assert data["unresolved_operations"] == []
    assert snapshot(x.path, x.owner.id, x.clock.value).requests_used == 5
    before = all_rows(x.path)
    assert x.admission.settle(item["id"], operation_count=99) == first
    assert all_rows(x.path) == before


def test_caller_owned_transaction_and_legacy_rows_remain_untouched_on_read(tmp_path):
    path = tmp_path / "transaction.sqlite3"
    tasks = TaskRunStore(path)
    first = record(tasks, "workX", title="Legacy task")
    with sqlite3.connect(path) as db:
        before = {name: db.execute(f"SELECT * FROM {name}").fetchall() for name in ("task_runs", "task_steps")}
    tasks.list_runs("owner")
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        assert {name: [tuple(row) for row in db.execute(f"SELECT * FROM {name}")] for name in before} == before
        db.execute("BEGIN IMMEDIATE")
        current = record(tasks, "work_", start=NOW + 2, connection=db, operation_id="stable")
        assert current != first and db.in_transaction
        assert record(tasks, "different", start=NOW + 50, connection=db, operation_id="stable") == current
        db.rollback()
        assert {name: [tuple(row) for row in db.execute(f"SELECT * FROM {name}")] for name in before} == before
    finally:
        db.close()
