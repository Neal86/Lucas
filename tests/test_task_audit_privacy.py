"""Audit privacy regressions using SQLite and a registry that never executes commands."""

import asyncio
import copy
import json
import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest

from gpt_windows_connector.auth import AuthStore, reset_current_user, set_current_user
from gpt_windows_connector.gateway_stores import NodeAuthStore, UserNodeBindingStore
from gpt_windows_connector.task_runs import TaskRunStore


def _record(store, details, *, operation_count=1, action="shell.run"):
    return store.record_operation(
        owner_id="audit-owner",
        node_id="audit-device",
        action=action,
        target="audit-workspace",
        started_at=100.0,
        ended_at=101.0,
        status="success",
        details=details,
        operation_count=operation_count,
        context_key="audit-context",
        task_title="Audit privacy check",
    )


def _stored_step(store):
    with sqlite3.connect(store.path) as db:
        db.row_factory = sqlite3.Row
        return dict(db.execute("SELECT * FROM task_steps").fetchone())


def test_store_never_persists_sub_operation_content_and_preserves_metadata(tmp_path):
    store = TaskRunStore(tmp_path / "tasks.db")
    # Include innocuous-looking values and command names, not just recognizable secrets.
    operations = [
        "curl -H 'Authorization: Bearer synthetic-audit-token' https://example.invalid",
        "Set-Content -Path private-file-name -Value ordinary-looking-private-data",
        "private-command-name --value confidential-argument",
        "npm publish --otp=123456",
        "Get-Content private-document\nsecond-private-line",
        {"command": "unexpected-structured-private-command"},
        None,
    ]
    metadata = {
        "source": "oauth",
        "agent": "audit-client",
        "task_title": "Audit privacy check",
        "session_id": "audit-session",
        "approval": {"decision": "approved_locally"},
        "result": {"exit_code": 0},
    }
    details = {**metadata, "sub_operations": operations}
    original = copy.deepcopy(details)
    run_id = _record(store, details, operation_count=11)

    stored = _stored_step(store)
    expected = {**metadata, "sub_operations": ["shell.run"] * len(operations)}
    assert json.loads(stored["details"]) == expected
    assert details == original  # Sanitizing audit data must not mutate accounting input.
    assert stored["operation_count"] == 11  # Never recompute billing from display labels.
    assert stored["owner_id"] == "audit-owner"
    assert stored["node_id"] == "audit-device"
    assert stored["action"] == "shell.run"
    assert stored["target"] == "audit-workspace"
    assert stored["status"] == "success"
    assert stored["duration_ms"] == 1000
    run = store.list_runs("audit-owner")[0]
    assert run["id"] == run_id
    assert run["title"] == "Audit privacy check"
    assert run["success_count"] == 1
    assert run["error_count"] == 0
    assert run["steps"][0]["details"] == expected


def test_legacy_sub_operations_are_hidden_without_rewriting_historical_rows(tmp_path):
    store = TaskRunStore(tmp_path / "tasks.db")
    _record(store, {}, operation_count=2)
    legacy_details = '{ "source": "account", "session_id": "legacy-session", "sub_operations": ["curl --password legacy-private-value", "legacy-private-command"] }'
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE task_steps SET details=?", (legacy_details,))
        original_runs = db.execute("SELECT * FROM task_runs").fetchall()
        original_steps = db.execute("SELECT * FROM task_steps").fetchall()

    for _ in range(2):
        step = store.list_runs("audit-owner")[0]["steps"][0]
        assert step["details"] == {
            "source": "account",
            "session_id": "legacy-session",
            "sub_operations": ["shell.run", "shell.run"],
        }
        assert step["operation_count"] == 2

    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT * FROM task_runs").fetchall() == original_runs
        assert db.execute("SELECT * FROM task_steps").fetchall() == original_steps


@pytest.mark.parametrize("value", [None, "raw-private-command", {"command": "raw-private-command"}, 7])
@pytest.mark.parametrize("legacy", [False, True])
def test_malformed_sub_operations_fail_closed_as_string_array(tmp_path, value, legacy):
    store = TaskRunStore(tmp_path / "tasks.db")
    details = {"agent": "audit-client", "sub_operations": value}
    _record(store, {} if legacy else details, operation_count=5)
    if legacy:
        with sqlite3.connect(store.path) as db:
            db.execute("UPDATE task_steps SET details=?", (json.dumps(details),))
    expected = {"agent": "audit-client", "sub_operations": []}
    assert store.list_runs("audit-owner")[0]["steps"][0]["details"] == expected
    assert json.loads(_stored_step(store)["details"]) == (details if legacy else expected)
    assert _stored_step(store)["operation_count"] == 5


@pytest.mark.parametrize("operations", [("private-command", "private-argument"), ["shell.run", "shell.run"]])
def test_tuple_inputs_and_repeated_sanitization_preserve_cardinality(tmp_path, operations):
    store = TaskRunStore(tmp_path / "tasks.db")
    _record(store, {"sub_operations": operations}, operation_count=2)
    expected = {"sub_operations": ["shell.run", "shell.run"]}
    assert json.loads(_stored_step(store)["details"]) == expected
    for _ in range(2):
        assert store.list_runs("audit-owner")[0]["steps"][0]["details"] == expected


@pytest.mark.parametrize("legacy_details", ["not-json", '"raw-private-command"', '["raw-private-command"]', "null"])
def test_malformed_legacy_details_are_safe_without_a_write(tmp_path, legacy_details):
    store = TaskRunStore(tmp_path / "tasks.db")
    _record(store, {})
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE task_steps SET details=?", (legacy_details,))
    assert store.list_runs("audit-owner")[0]["steps"][0]["details"] == {}
    assert _stored_step(store)["details"] == legacy_details


@pytest.mark.parametrize("details", [{}, {"source": "account"}, {"sub_operations": []}])
def test_unrelated_details_and_empty_operation_lists_are_unchanged(tmp_path, details):
    store = TaskRunStore(tmp_path / "tasks.db")
    _record(store, details, action="browser.inspect")
    assert json.loads(_stored_step(store)["details"]) == details
    assert store.list_runs("audit-owner")[0]["steps"][0]["details"] == details


@pytest.fixture
def gateway_audit(tmp_path, monkeypatch):
    # Any first-time gateway initialization is also isolated from application data.
    monkeypatch.setenv("GWC_DATA_DIR", str(tmp_path / "gateway-bootstrap"))
    monkeypatch.setenv("LUCAS_BETA_FREE", "1")
    from gpt_windows_connector import gateway

    path = tmp_path / "gateway-test.db"
    auth = AuthStore(path, "synthetic-audit-test-signing-key-" * 2)
    user = auth.register("audit@example.invalid", "synthetic-audit-password")
    NodeAuthStore(path)
    UserNodeBindingStore(path).upsert(user.id, "audit-device")
    store = TaskRunStore(path)
    monkeypatch.setattr(gateway, "db_path", path)
    monkeypatch.setattr(gateway, "auth", auth)
    monkeypatch.setattr(gateway, "task_runs", store)
    return SimpleNamespace(gateway=gateway, auth=auth, store=store, user=user)


@pytest.mark.parametrize(
    ("outcome", "client_id"),
    [("success", "audit-client"), ("success", None), ("failure", "audit-client"), ("runtime", "audit-client")],
)
def test_gateway_audit_paths_preserve_accounting_without_command_details(gateway_audit, monkeypatch, outcome, client_id):
    gateway = gateway_audit.gateway
    user = replace(gateway_audit.user, client_id=client_id)
    if outcome == "runtime":
        command = "Set-Content -Path private-runtime-path -Value private-runtime-value"
        # Repeated execution has three runtime operations but only one static action.
        stdout = (f"DEBUG:    3+   >>>> {command}\n" * 3) + "visible output\n"
        expected_count = 3
    else:
        command = "curl --header 'Authorization: Bearer private-static-value' https://example.invalid\nnpm publish --otp=private-otp"
        stdout = "visible output\n"
        expected_count = 2

    class HarmlessRegistry:
        def __init__(self):
            self.calls = []

        async def rpc(self, node_id, owner_id, method, payload, *, actor, timeout):
            self.calls.append((node_id, owner_id, method, copy.deepcopy(payload), actor, timeout))
            if outcome == "failure":
                raise RuntimeError("synthetic registry failure")
            return {"stdout": stdout, "stderr": "", "exit_code": 0}

    registry = HarmlessRegistry()
    monkeypatch.setattr(gateway, "registry", registry)
    payload = {
        "command": command,
        "shell_type": "powershell" if outcome == "runtime" else "cmd",
        "session_id": "audit-session",
    }
    original_payload = copy.deepcopy(payload)
    context = set_current_user(user)
    try:
        call = gateway._node_rpc(
            "audit-device", "audit-workspace", "shell.run", payload,
            task_title="Audit privacy check",
        )
        if outcome == "failure":
            with pytest.raises(RuntimeError, match="synthetic registry failure"):
                asyncio.run(call)
        else:
            assert asyncio.run(call) == {"stdout": "visible output\n", "stderr": "", "exit_code": 0}
    finally:
        reset_current_user(context)

    assert payload == original_payload
    assert len(registry.calls) == 1
    sent = registry.calls[0]
    assert sent[:3] == ("audit-device", user.id, "shell.run")
    assert sent[3]["command"] == (gateway._instrument_powershell(command) if outcome == "runtime" else command)
    assert sent[3]["session_id"] == "audit-session"
    assert sent[4]["agent"] == client_id
    assert sent[4]["task_title"] == "Audit privacy check"

    stored = _stored_step(gateway_audit.store)
    details = json.loads(stored["details"])
    expected_status = "failed" if outcome == "failure" else "success"
    assert details["sub_operations"] == ["shell.run"] * expected_count
    assert details["source"] == ("oauth" if client_id else "account")
    assert details["agent"] == client_id
    assert details["session_id"] == "audit-session"
    assert details["task_title"] == "Audit privacy check"
    if outcome == "failure":
        assert details["error_type"] == "RuntimeError"
    assert stored["owner_id"] == user.id
    assert stored["node_id"] == "audit-device"
    assert stored["status"] == expected_status
    assert stored["operation_count"] == expected_count
    run = gateway_audit.store.list_runs(user.id)[0]
    assert run["steps"][0]["details"] == details
    assert run["success_count"] == (0 if outcome == "failure" else 1)
    assert run["error_count"] == (1 if outcome == "failure" else 0)

    with sqlite3.connect(gateway_audit.store.path) as db:
        usage = db.execute("SELECT operation_count,success_count,error_count FROM usage_daily WHERE user_id=?", (user.id,)).fetchone()
        audit = db.execute("SELECT details FROM audit_logs WHERE user_id=? AND action='shell.run'", (user.id,)).fetchone()
    expected_usage = (expected_count, 0, expected_count) if outcome == "failure" else (expected_count, expected_count, 0)
    assert usage == expected_usage
    audit_details = json.loads(audit[0])
    assert audit_details["status"] == expected_status
    assert audit_details["operation_count"] == expected_count
    assert audit_details["node_id"] == "audit-device"
    assert audit_details["session_id"] == "audit-session"
    assert audit_details["agent"] == client_id
    assert "private-" not in stored["details"]
    assert "private-" not in audit[0]
