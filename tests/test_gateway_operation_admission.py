"""Exercise operation admission at the real gateway boundary using disposable SQLite.

Only Node dispatch is faked: no Node, browser, network endpoint, user store, or
external command is contacted. The same race tests run against the pre-fix tree.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from types import SimpleNamespace

import pytest

from gpt_windows_connector.auth import AuthStore, reset_current_user, set_current_user
from gpt_windows_connector.entitlements import snapshot
from gpt_windows_connector.gateway_stores import NodeAuthStore, UserNodeBindingStore
from gpt_windows_connector.task_runs import TaskRunStore


@pytest.fixture
def operation_gateway(tmp_path, monkeypatch):
    from gpt_windows_connector import gateway
    from gpt_windows_connector.gateway_registry import NodeRegistry

    monkeypatch.setenv("LUCAS_BETA_FREE", "1")
    monkeypatch.delenv("GWC_SUPER_ADMIN_EMAIL", raising=False)
    db_path = tmp_path / "operation-admission.sqlite3"
    auth = AuthStore(db_path, "synthetic-operation-admission-secret-only")
    tasks = TaskRunStore(db_path)
    nodes = NodeAuthStore(db_path)
    bindings = UserNodeBindingStore(db_path)
    user = auth.register("operation-fixture@example.test", "synthetic-fixture-password")
    node_id = "synthetic-operation-node"
    workspace = r"C:\Synthetic\Allowed"
    asyncio.run(nodes.save(node_id, "Synthetic fixture", "synthetic-node-token", [workspace]))
    bindings.upsert(user.id, node_id)
    registry = NodeRegistry(bindings)
    for name, value in {
        "db_path": db_path,
        "auth": auth,
        "task_runs": tasks,
        "auth_store": nodes,
        "bindings": bindings,
        "registry": registry,
    }.items():
        monkeypatch.setattr(gateway, name, value)
    context = set_current_user(user)
    try:
        yield SimpleNamespace(
            gateway=gateway, path=db_path, auth=auth, tasks=tasks, nodes=nodes,
            bindings=bindings, user=user, node_id=node_id, workspace=workspace,
        )
    finally:
        reset_current_user(context)


def _seed_operations(env, count):
    now = time.time()
    env.tasks.record_operation(
        owner_id=env.user.id, node_id=env.node_id, action="fixture.seed",
        target=env.workspace, started_at=now, ended_at=now, status="success",
        operation_count=count,
    )


def _rows(env, table):
    with sqlite3.connect(env.path) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(f"SELECT * FROM {table}")]


def _run(env, method="workspace.info", params=None, **kwargs):
    return asyncio.run(env.gateway._node_rpc(env.node_id, env.workspace, method, params, **kwargs))


def _overlapping_calls(env, monkeypatch):
    """Hold every dispatched RPC until both gateway coroutines have had a turn."""
    async def scenario():
        gate = asyncio.Event()
        entered = asyncio.Event()
        dispatched = []

        async def rpc(*args, **kwargs):
            dispatched.append((args, kwargs))
            entered.set()
            await gate.wait()
            return {"ok": True}

        monkeypatch.setattr(env.gateway.registry, "rpc", rpc)
        first = asyncio.create_task(env.gateway._node_rpc(env.node_id, env.workspace, "workspace.info"))
        await asyncio.wait_for(entered.wait(), timeout=2)
        second = asyncio.create_task(env.gateway._node_rpc(env.node_id, env.workspace, "workspace.info"))
        await asyncio.sleep(0)
        simultaneous = len(dispatched)
        in_flight = snapshot(env.path, env.user.id)
        gate.set()
        outcomes = await asyncio.gather(first, second, return_exceptions=True)
        return simultaneous, in_flight, outcomes

    return asyncio.run(scenario())


def test_gateway_concurrent_last_operation_admits_exactly_one(operation_gateway, monkeypatch):
    env = operation_gateway
    _seed_operations(env, 99_999)
    simultaneous, in_flight, outcomes = _overlapping_calls(env, monkeypatch)

    assert simultaneous == 1, "both RPCs passed the 99,999/100,000 gateway admission check"
    assert sum(isinstance(outcome, PermissionError) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, dict) for outcome in outcomes) == 1
    assert in_flight.requests_used == 99_999
    assert in_flight.requests_pending == 1
    assert in_flight.requests_unconfirmed == 0
    assert in_flight.as_dict()["request_remaining"] == 0
    assert snapshot(env.path, env.user.id).requests_used == 100_000


def test_gateway_below_limit_operations_remain_concurrent(operation_gateway, monkeypatch):
    env = operation_gateway
    simultaneous, in_flight, outcomes = _overlapping_calls(env, monkeypatch)

    assert simultaneous == 2, "admission must not serialize remote execution below quota"
    assert outcomes == [{"ok": True}, {"ok": True}]
    assert in_flight.requests_used == 0
    assert in_flight.requests_pending == 2
    assert snapshot(env.path, env.user.id).requests_used == 2


def _assert_completed_accounting(env, *, status, count=1):
    entitlements = snapshot(env.path, env.user.id)
    assert (entitlements.requests_used, entitlements.requests_pending, entitlements.requests_unconfirmed) == (count, 0, 0)
    steps = _rows(env, "task_steps")
    audits = [row for row in _rows(env, "audit_logs") if row["action"] == "workspace.info"]
    usage = _rows(env, "usage_daily")
    reservations = _rows(env, "operation_reservations")
    assert len(steps) == len(audits) == len(usage) == len(reservations) == 1
    assert steps[0]["status"] == status
    assert steps[0]["operation_count"] == count
    assert json.loads(audits[0]["details"])["status"] == status
    assert json.loads(audits[0]["details"])["operation_count"] == count
    assert usage[0]["operation_count"] == count
    assert usage[0]["success_count"] == (count if status == "success" else 0)
    assert usage[0]["error_count"] == (count if status == "failed" else 0)
    assert reservations[0]["status"] == "settled"
    assert reservations[0]["outcome"] == status
    assert reservations[0]["id"] == steps[0]["id"]
    assert len(env.tasks.list_runs(env.user.id)[0]["steps"]) == 1


def test_gateway_success_settles_one_atomic_accounting_record(operation_gateway, monkeypatch):
    env = operation_gateway
    result = {"synthetic": "result"}
    dispatches = []

    async def rpc(*args, **kwargs):
        dispatches.append((args, kwargs))
        assert snapshot(env.path, env.user.id).requests_pending == 1
        return result

    monkeypatch.setattr(env.gateway.registry, "rpc", rpc)
    assert _run(env) is result
    assert len(dispatches) == 1
    assert dispatches[0][0][:3] == (env.node_id, env.user.id, "workspace.info")
    _assert_completed_accounting(env, status="success")


def test_gateway_confirmed_node_error_counts_failure_once(operation_gateway, monkeypatch):
    from gpt_windows_connector.gateway_registry import ConfirmedNodeError

    env = operation_gateway
    failure = ConfirmedNodeError("synthetic-remote-error-private-value")
    dispatches = []

    async def rpc(*args, **kwargs):
        dispatches.append(args)
        raise failure

    monkeypatch.setattr(env.gateway.registry, "rpc", rpc)
    with pytest.raises(ConfirmedNodeError) as caught:
        _run(env)
    assert caught.value is failure
    assert len(dispatches) == 1
    _assert_completed_accounting(env, status="failed")
    persisted = json.dumps(_rows(env, "audit_logs") + _rows(env, "task_steps") + _rows(env, "operation_reservations"))
    assert str(failure) not in persisted


@pytest.mark.parametrize("error_class", [TimeoutError, ConnectionError, RuntimeError])
def test_gateway_transport_failure_holds_minimum_without_false_failure(operation_gateway, monkeypatch, error_class):
    env = operation_gateway
    _seed_operations(env, 99_999)
    failure = error_class("synthetic-unknown-outcome-private-value")
    dispatches = []

    async def rpc(*args, **kwargs):
        dispatches.append(args)
        raise failure

    monkeypatch.setattr(env.gateway.registry, "rpc", rpc)
    with pytest.raises(error_class) as caught:
        _run(env, "shell.run", {"command": "Get-Item a; Get-Item b; Get-Item c", "shell_type": "cmd"})
    assert caught.value is failure
    entitlements = snapshot(env.path, env.user.id)
    assert (entitlements.requests_used, entitlements.requests_pending, entitlements.requests_unconfirmed) == (99_999, 0, 1)
    assert entitlements.as_dict()["request_remaining"] == 0
    assert all(row["action"] == "fixture.seed" for row in _rows(env, "task_steps"))
    assert not _rows(env, "usage_daily")
    reservation, = _rows(env, "operation_reservations")
    assert reservation["status"] == "outcome_unconfirmed"
    assert reservation["reserved_operations"] == 1
    assert reservation["outcome"] in (None, "")
    persisted = json.dumps(_rows(env, "audit_logs") + [reservation])
    assert str(failure) not in persisted
    assert not any(json.loads(row["details"]).get("status") == "failed" for row in _rows(env, "audit_logs"))
    with pytest.raises(PermissionError):
        _run(env)
    assert len(dispatches) == 1, "unknown outcomes must neither be replayed nor silently refunded"


def test_gateway_cancellation_preserves_unknown_minimum(operation_gateway, monkeypatch):
    env = operation_gateway

    async def scenario():
        entered = asyncio.Event()
        never = asyncio.Event()
        dispatches = []

        async def rpc(*args, **kwargs):
            dispatches.append(args)
            entered.set()
            await never.wait()

        monkeypatch.setattr(env.gateway.registry, "rpc", rpc)
        task = asyncio.create_task(env.gateway._node_rpc(env.node_id, env.workspace, "workspace.info"))
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return dispatches

    assert len(asyncio.run(scenario())) == 1
    entitlements = snapshot(env.path, env.user.id)
    assert (entitlements.requests_used, entitlements.requests_pending, entitlements.requests_unconfirmed) == (0, 0, 1)
    assert not _rows(env, "task_steps")
    assert not _rows(env, "usage_daily")
    reservation, = _rows(env, "operation_reservations")
    assert reservation["status"] == "outcome_unconfirmed"
    assert reservation["reserved_operations"] == 1


@pytest.mark.parametrize("fault_target", ["task_steps", "usage_daily", "audit_logs", "operation_reservations"])
@pytest.mark.parametrize("remote_failed", [False, True], ids=["remote-success", "confirmed-failure"])
def test_gateway_bookkeeping_failure_rolls_back_without_reexecution(
    operation_gateway, monkeypatch, fault_target, remote_failed,
):
    from gpt_windows_connector.gateway_registry import ConfirmedNodeError

    env = operation_gateway
    dispatches = []
    result = {"synthetic": "successful-remote-result"}
    failure = ConfirmedNodeError("synthetic-confirmed-remote-error")

    async def rpc(*args, **kwargs):
        dispatches.append(args)
        with sqlite3.connect(env.path) as db:
            if fault_target == "operation_reservations":
                db.execute("""CREATE TRIGGER fixture_reject_settlement
                    BEFORE UPDATE ON operation_reservations WHEN NEW.status='settled'
                    BEGIN SELECT RAISE(ABORT, 'synthetic-settlement-fault'); END""")
            else:
                condition = " WHEN NEW.action='workspace.info'" if fault_target == "audit_logs" else ""
                db.execute(f"""CREATE TRIGGER fixture_reject_settlement
                    BEFORE INSERT ON {fault_target}{condition}
                    BEGIN SELECT RAISE(ABORT, 'synthetic-settlement-fault'); END""")
        if remote_failed:
            raise failure
        return result

    monkeypatch.setattr(env.gateway.registry, "rpc", rpc)
    if remote_failed:
        with pytest.raises(ConfirmedNodeError) as caught:
            _run(env)
        assert caught.value is failure
    else:
        assert _run(env) is result, "accounting failure must not turn a known remote success into a retry signal"
    assert len(dispatches) == 1
    for table in ("task_steps", "task_runs", "usage_daily"):
        assert not _rows(env, table), f"partial settlement escaped rollback in {table}"
    assert not any(row["action"] == "workspace.info" for row in _rows(env, "audit_logs"))
    reservation, = _rows(env, "operation_reservations")
    assert reservation["status"] == "outcome_unconfirmed"
    assert reservation["reserved_operations"] == 1
    entitlements = snapshot(env.path, env.user.id)
    assert (entitlements.requests_used, entitlements.requests_pending, entitlements.requests_unconfirmed) == (0, 0, 1)


@pytest.mark.parametrize("runtime_trace", [False, True], ids=["static-fallback", "runtime-loop"])
def test_gateway_shell_reserves_minimum_then_records_actual_count(operation_gateway, monkeypatch, runtime_trace):
    env = operation_gateway
    _seed_operations(env, 99_999)
    dispatched = []
    if runtime_trace:
        command = 'foreach ($item in 1..3) {\n  Get-Item fixture\n}'
        stdout = 'DEBUG:    4+   >>>> Get-Item fixture\n' * 3 + "visible result\n"
        params = {"command": command, "shell_type": "powershell", "timeout": 600}
    else:
        params = {"command": "Get-Item a; Get-Item b; Get-Item c", "shell_type": "cmd", "timeout": 600}
        stdout = "visible result\n"

    async def rpc(*args, **kwargs):
        dispatched.append((args, kwargs))
        entitlements = snapshot(env.path, env.user.id)
        assert entitlements.requests_pending == 1
        assert entitlements.requests_used == 99_999
        return {"stdout": stdout, "exit_code": 0}

    monkeypatch.setattr(env.gateway.registry, "rpc", rpc)
    result = _run(env, "shell.run", params)
    assert result["stdout"] == "visible result\n"
    assert len(dispatched) == 1
    assert dispatched[0][1]["timeout"] == 660.0
    assert snapshot(env.path, env.user.id).requests_used == 100_002
    step = next(row for row in _rows(env, "task_steps") if row["action"] == "shell.run")
    assert step["operation_count"] == 3
    assert json.loads(step["details"])["sub_operations"] == ["shell.run"] * 3
    assert _rows(env, "usage_daily")[0]["operation_count"] == 3
    with pytest.raises(PermissionError):
        _run(env)
    assert len(dispatched) == 1, "a dynamic shell may cross quota, but the next operation must be blocked"


def test_gateway_completion_stays_in_admission_month_and_day(operation_gateway, monkeypatch):
    from datetime import datetime, timezone

    env = operation_gateway
    boundary = datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp()
    started = boundary - 0.25
    ended = boundary + 10
    clock = SimpleNamespace(now=started)
    monkeypatch.setattr(time, "time", lambda: clock.now)

    async def rpc(*args, **kwargs):
        reservation, = _rows(env, "operation_reservations")
        assert reservation["started_at"] == started
        assert reservation["period_end"] == boundary
        clock.now = ended
        return {"ok": True}

    monkeypatch.setattr(env.gateway.registry, "rpc", rpc)
    assert _run(env) == {"ok": True}
    step, = _rows(env, "task_steps")
    reservation, = _rows(env, "operation_reservations")
    assert step["started_at"] == reservation["started_at"] == started
    assert step["ended_at"] == ended
    assert _rows(env, "usage_daily")[0]["day"] == "2026-10-31"
    assert snapshot(env.path, env.user.id, now=started).requests_used == 1
    current = snapshot(env.path, env.user.id, now=ended)
    assert (current.requests_used, current.requests_pending, current.requests_unconfirmed) == (0, 0, 0)


def test_gateway_reservation_and_history_never_store_shell_payloads(operation_gateway, monkeypatch):
    env = operation_gateway
    private = "SYNTHETIC_COMMAND_VALUE_NOT_FOR_HISTORY"
    command = f'Set-Content fixture.txt "{private}"; Get-Item fixture.txt'
    params = {"command": command, "shell_type": "cmd", "session_id": "synthetic-session", "content": private}

    async def rpc(*args, **kwargs):
        assert args[3]["command"] == command
        pending = _rows(env, "operation_reservations")
        assert len(pending) == 1
        assert private not in json.dumps(pending)
        assert command not in json.dumps(pending)
        return {"stdout": private, "exit_code": 0}

    monkeypatch.setattr(env.gateway.registry, "rpc", rpc)
    assert _run(env, "shell.run", params, task_title="  Synthetic   review  ")["stdout"] == private
    for table in ("operation_reservations", "task_steps", "task_runs", "audit_logs"):
        assert private not in json.dumps(_rows(env, table)), table
    runs = env.tasks.list_runs(env.user.id)
    assert runs[0]["title"] == "Synthetic review"
    details = runs[0]["steps"][0]["details"]
    assert details["sub_operations"] == ["shell.run", "shell.run"]
    assert details["session_id"] == "synthetic-session"
    assert private not in json.dumps(runs)


def test_http_task_history_labels_pending_and_unknown_without_cross_owner_leak(operation_gateway, monkeypatch):
    import httpx
    from gpt_windows_connector import webapp

    env = operation_gateway
    other = env.auth.register("other-operation-fixture@example.test", "synthetic-other-password")
    owner_headers = {"Authorization": "Bearer " + env.auth.issue_token(env.user)}
    other_headers = {"Authorization": "Bearer " + env.auth.issue_token(other)}
    private = "SYNTHETIC_HTTP_COMMAND_NOT_FOR_HISTORY"

    async def scenario():
        entered = asyncio.Event()
        gate = asyncio.Event()

        async def rpc(*args, **kwargs):
            entered.set()
            await gate.wait()
            raise TimeoutError(private)

        monkeypatch.setattr(env.gateway.registry, "rpc", rpc)
        task = asyncio.create_task(env.gateway._node_rpc(
            env.node_id, env.workspace, "shell.run", {"command": f"Get-Item {private}", "shell_type": "cmd"},
        ))
        await asyncio.wait_for(entered.wait(), timeout=2)
        transport = httpx.ASGITransport(app=webapp.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://synthetic.test") as client:
            pending = await client.get("/api/task-runs", headers=owner_headers)
            assert pending.status_code == 200
            body = pending.json()
            assert body["summary"]["operations"] == 0
            assert body["runs"] == []
            held, = body["unresolved_operations"]
            assert held["status"] == "pending"
            assert held["reserved_operations"] == 1
            assert held["currently_held"] is True
            assert private not in pending.text

            other_response = await client.get("/api/task-runs", headers=other_headers)
            assert other_response.status_code == 200
            assert other_response.json()["unresolved_operations"] == []
            assert other_response.json()["runs"] == []
            assert held["id"] not in other_response.text
            filtered = await client.get("/api/task-runs?node_id=another-synthetic-node", headers=owner_headers)
            assert filtered.status_code == 200
            assert filtered.json()["unresolved_operations"] == []

            gate.set()
            with pytest.raises(TimeoutError):
                await task
            unknown = await client.get("/api/task-runs", headers=owner_headers)
            assert unknown.status_code == 200
            body = unknown.json()
            assert body["summary"]["operations"] == 0
            assert body["runs"] == []
            unresolved, = body["unresolved_operations"]
            assert unresolved["id"] == held["id"]
            assert unresolved["status"] == "outcome_unconfirmed"
            assert unresolved["reserved_operations"] == 1
            assert unresolved["currently_held"] is True
            assert private not in unknown.text
            logs = await client.get("/api/logs", headers=owner_headers)
            assert logs.status_code == 200
            assert private not in logs.text
            assert not any(log["details"].get("status") == "failed" for log in logs.json()["logs"])

    asyncio.run(scenario())


def test_unknown_outcome_survives_deadline_and_rollover_as_history(operation_gateway, monkeypatch):
    from datetime import datetime, timezone
    from gpt_windows_connector.operation_admission import list_unresolved

    env = operation_gateway
    boundary = datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp()
    clock = SimpleNamespace(now=boundary - 600)
    monkeypatch.setattr(time, "time", lambda: clock.now)
    _seed_operations(env, 99_999)
    dispatches = []

    async def rpc(*args, **kwargs):
        dispatches.append(args)
        raise TimeoutError("synthetic-unconfirmed-result")

    monkeypatch.setattr(env.gateway.registry, "rpc", rpc)
    with pytest.raises(TimeoutError):
        _run(env)
    reservation, = _rows(env, "operation_reservations")
    clock.now = reservation["deadline_at"] + 1
    assert clock.now < boundary
    held = snapshot(env.path, env.user.id)
    assert (held.requests_used, held.requests_unconfirmed) == (99_999, 1)
    with pytest.raises(PermissionError):
        _run(env)
    assert len(dispatches) == 1

    clock.now = boundary + 1
    current = snapshot(env.path, env.user.id)
    assert (current.requests_used, current.requests_pending, current.requests_unconfirmed) == (0, 0, 0)
    history, = list_unresolved(env.path, env.user.id)
    assert history["id"] == reservation["id"]
    assert history["status"] == "outcome_unconfirmed"
    assert history["currently_held"] is False
    assert history["reserved_operations"] == 1
    assert not any(row["action"] != "fixture.seed" for row in _rows(env, "task_steps"))


def test_registry_negative_reply_has_explicit_confirmed_failure_type(operation_gateway):
    from gpt_windows_connector.gateway_registry import ConfirmedNodeError

    env = operation_gateway

    async def scenario():
        future = asyncio.get_running_loop().create_future()
        env.gateway.registry.pending_requests[env.node_id] = {"synthetic-request": future}
        env.gateway.registry.resolve(env.node_id, {"id": "synthetic-request", "ok": False, "error": "synthetic remote rejection"})
        with pytest.raises(ConfirmedNodeError, match="synthetic remote rejection"):
            await future
        assert isinstance(future.exception(), RuntimeError)

    asyncio.run(scenario())


@pytest.mark.parametrize("remote_failed", [False, True], ids=["remote-success", "confirmed-failure"])
def test_gateway_double_accounting_failure_keeps_durable_hold(operation_gateway, monkeypatch, remote_failed):
    from gpt_windows_connector.gateway_registry import ConfirmedNodeError

    env = operation_gateway
    period = snapshot(env.path, env.user.id)
    middle_of_month = (period.period_start + period.period_end) / 2
    monkeypatch.setattr(time, "time", lambda: middle_of_month)
    dispatches = []
    failure = ConfirmedNodeError("synthetic-confirmed-error-under-accounting-fault")

    async def rpc(*args, **kwargs):
        dispatches.append(args)
        with sqlite3.connect(env.path) as db:
            db.execute("""CREATE TRIGGER fixture_reject_all_audit
                BEFORE INSERT ON audit_logs
                BEGIN SELECT RAISE(ABORT, 'synthetic-total-accounting-fault'); END""")
        if remote_failed:
            raise failure
        return {"ok": True}

    monkeypatch.setattr(env.gateway.registry, "rpc", rpc)
    if remote_failed:
        with pytest.raises(ConfirmedNodeError) as caught:
            _run(env)
        assert caught.value is failure
    else:
        assert _run(env) == {"ok": True}
    assert len(dispatches) == 1
    for table in ("task_runs", "task_steps", "usage_daily"):
        assert not _rows(env, table)
    held = snapshot(env.path, env.user.id)
    assert (held.requests_used, held.requests_pending, held.requests_unconfirmed) == (0, 1, 0)
    reservation, = _rows(env, "operation_reservations")
    assert reservation["status"] == "pending"
    assert reservation["reserved_operations"] == 1

    # A failed annotation never releases the durable reservation. Once the
    # fixture database recovers, its deadline changes the label, not the charge.
    with sqlite3.connect(env.path) as db:
        db.execute("DROP TRIGGER fixture_reject_all_audit")
    recovered = snapshot(env.path, env.user.id, now=reservation["deadline_at"] + 1)
    assert (recovered.requests_used, recovered.requests_pending, recovered.requests_unconfirmed) == (0, 0, 1)
    assert len(dispatches) == 1
    assert not _rows(env, "task_steps")


@pytest.mark.parametrize("blocker", ["blank-workspace", "inactive-node", "quota-exhausted"])
def test_gateway_preflight_denial_does_not_reserve_or_dispatch(operation_gateway, monkeypatch, blocker):
    env = operation_gateway
    workspace = env.workspace
    if blocker == "blank-workspace":
        workspace = "  "
        expected = ValueError
    elif blocker == "inactive-node":
        for i in range(3):
            env.bindings.upsert(env.user.id, f"newer-synthetic-node-{i}")
        expected = PermissionError
    else:
        _seed_operations(env, 100_000)
        expected = PermissionError

    async def rpc(*args, **kwargs):
        pytest.fail("preflight-rejected operation reached remote dispatch")

    monkeypatch.setattr(env.gateway.registry, "rpc", rpc)
    with pytest.raises(expected):
        asyncio.run(env.gateway._node_rpc(env.node_id, workspace, "workspace.info"))
    with sqlite3.connect(env.path) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='operation_reservations'").fetchone()
        if exists:
            assert db.execute("SELECT COUNT(*) FROM operation_reservations").fetchone()[0] == 0
    assert not _rows(env, "audit_logs")
    assert not _rows(env, "usage_daily")
    assert all(row["action"] == "fixture.seed" for row in _rows(env, "task_steps"))
