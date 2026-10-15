"""Activation stays atomic on real SQLite, including retries from stale dashboards."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing, contextmanager
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from gpt_windows_connector import entitlements
from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector.billing import BillingService


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    for variable in ("HOME", "LOCALAPPDATA", "GWC_DATA_DIR"):
        directory = tmp_path / variable.lower()
        directory.mkdir()
        monkeypatch.setenv(variable, str(directory))
    monkeypatch.setenv("LUCAS_BETA_FREE", "1")
    monkeypatch.delenv("GWC_SUPER_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)


@pytest.fixture
def short_connections(monkeypatch):
    """Use real connections; make a nested-writer regression fail in 50 ms."""
    opened = []

    @contextmanager
    def connect(path):
        with closing(sqlite3.connect(path, timeout=0.05)) as db:
            db.row_factory = sqlite3.Row
            opened.append(path)
            with db:
                yield db

    monkeypatch.setattr(entitlements, "_connect", connect)
    return opened


@pytest.fixture
def database(tmp_path, short_connections, request):
    journal_mode = getattr(request.node, "callspec", SimpleNamespace(params={})).params.get("journal_mode", "WAL")
    path = tmp_path / "activation.db"
    with sqlite3.connect(path) as db:
        db.execute(f"PRAGMA journal_mode={journal_mode}")
        db.executescript("""
            CREATE TABLE users(id TEXT PRIMARY KEY,role TEXT);
            CREATE TABLE subscriptions(
                user_id TEXT PRIMARY KEY,plan TEXT,status TEXT,
                expansion_quantity INTEGER DEFAULT 0,current_period_start REAL,
                current_period_end REAL,cancel_at_period_end INTEGER DEFAULT 0,
                bonus_requests INTEGER DEFAULT 0
            );
            CREATE TABLE user_node_bindings(
                user_id TEXT,node_id TEXT,approved_at REAL,updated_at REAL,
                PRIMARY KEY(user_id,node_id)
            );
            CREATE TABLE oauth_client_users(client_id TEXT,user_id TEXT,authorized_at REAL);
            INSERT INTO users VALUES('owner','user');
        """)
    bind_nodes(path, "owner", 4)
    entitlements.active_node_ids(path, "owner")
    short_connections.clear()
    return path


def bind_nodes(path, owner, count):
    with sqlite3.connect(path) as db:
        db.executemany(
            "INSERT INTO user_node_bindings VALUES(?,?,?,?)",
            [(owner, f"node-{i}", i + 1, i + 1) for i in range(count)],
        )


def active_rows(path, owner="owner"):
    with sqlite3.connect(path) as db:
        return db.execute(
            "SELECT node_id,manual,activated_at FROM user_active_nodes "
            "WHERE user_id=? ORDER BY node_id", (owner,),
        ).fetchall()


def binding_rows(path):
    with sqlite3.connect(path) as db:
        return db.execute("SELECT * FROM user_node_bindings ORDER BY user_id,node_id").fetchall()


@pytest.mark.parametrize("journal_mode", ["DELETE", "WAL"])
@pytest.mark.parametrize("manual", [0, 1])
def test_reactivate_uses_one_transaction_and_preserves_manual_selection(
    database, short_connections, journal_mode, manual,
):
    with sqlite3.connect(database) as db:
        db.execute(
            "UPDATE user_active_nodes SET manual=?,activated_at=1 "
            "WHERE user_id='owner' AND node_id='node-2'", (manual,),
        )
    before = {row[0] for row in active_rows(database)}
    bindings = binding_rows(database)

    active = entitlements.set_active_node(database, "owner", " node-2 ")

    assert len(short_connections) == 1
    assert set(active) == before
    rows = {node: (flag, activated) for node, flag, activated in active_rows(database)}
    assert rows["node-2"][0] == 1
    assert rows["node-2"][1] > 1
    assert all(flag == 0 for node, (flag, _) in rows.items() if node != "node-2")
    assert binding_rows(database) == bindings
    # The manual selection survives a later dashboard refresh preferring other nodes.
    refreshed = entitlements.active_node_ids(database, "owner", ["node-0", "node-1", "node-3"])
    assert len(refreshed) == 3 and "node-2" in refreshed


def test_stale_activation_retry_does_not_swap_out_another_computer(database, short_connections):
    assert "node-0" not in {row[0] for row in active_rows(database)}
    first = entitlements.set_active_node(database, "owner", "node-0")
    assert len(first) == 3 and "node-0" in first
    for _ in range(3):
        short_connections.clear()
        assert set(entitlements.set_active_node(database, "owner", "node-0")) == set(first)
        assert len(short_connections) == 1
    assert dict((node, manual) for node, manual, _ in active_rows(database))["node-0"] == 1
    assert len(binding_rows(database)) == 4


@pytest.mark.parametrize("all_manual", [False, True])
def test_switch_evicts_auto_before_manual_then_oldest_manual(database, all_manual):
    with sqlite3.connect(database) as db:
        db.executemany(
            "UPDATE user_active_nodes SET manual=?,activated_at=? WHERE user_id='owner' AND node_id=?",
            [(1, 1, "node-1"), (int(all_manual), 2, "node-2"), (int(all_manual), 3, "node-3")],
        )
    active = set(entitlements.set_active_node(database, "owner", "node-0"))
    assert len(active) == 3 and "node-0" in active
    if all_manual:
        assert active == {"node-0", "node-2", "node-3"}
    else:
        assert "node-1" in active
        assert len(active & {"node-2", "node-3"}) == 1
    assert len(binding_rows(database)) == 4


@pytest.mark.parametrize(
    "beta,plan,status,expansion,role,bonus_nodes,expired,expected",
    [
        ("1", "free", "inactive", 0, "user", 0, False, 3),
        ("1", "pro_plus", "active", 2, "admin", 0, False, 3),
        ("1", "free", "inactive", 0, "user", 2, False, 5),
        ("1", "free", "inactive", 0, "user", 2, True, 3),
        ("0", "pro", "active", 2, "user", 0, False, 3),
        ("0", "pro_plus", "active", 0, "user", 0, False, 6),
        ("0", "pro_plus", "active", 1, "user", 0, False, 12),
        ("0", "pro_plus", "canceled", 1, "user", 0, False, 3),
        ("0", "free", "inactive", 0, "admin", 0, False, 6),
        ("0", "pro_plus", "active", 0, "user", 2, False, 8),
    ],
)
def test_repeat_activation_preserves_effective_limits(
    database, monkeypatch, beta, plan, status, expansion, role, bonus_nodes, expired, expected,
):
    monkeypatch.setenv("LUCAS_BETA_FREE", beta)
    now = time.time()
    with sqlite3.connect(database) as db:
        db.execute("UPDATE users SET role=? WHERE id='owner'", (role,))
        db.execute(
            "INSERT INTO subscriptions VALUES(?,?,?,?,?,?,?,?)",
            ("owner", plan, status, expansion, now - 100, now + 10000, 0, 0),
        )
        db.execute(
            "INSERT INTO entitlement_overrides VALUES(?,?,?,?,?,?)",
            ("owner", 0, bonus_nodes, 0, now - 1 if expired else now + 10000, now),
        )
        db.executemany(
            "INSERT INTO user_node_bindings VALUES(?,?,?,?)",
            [("owner", f"node-{i}", i + 1, i + 1) for i in range(4, 14)],
        )
        subscription = db.execute("SELECT * FROM subscriptions").fetchall()
    before = entitlements.snapshot(database, "owner")
    assert before.node_limit == expected
    current = entitlements.active_node_ids(database, "owner")
    active = entitlements.set_active_node(database, "owner", current[0])
    assert len(active) == expected and set(active) == set(current)
    after = entitlements.snapshot(database, "owner")
    assert (after.node_limit, after.nodes_used, after.nodes_connected) == (expected, expected, 14)
    assert (after.plan, after.expansion_quantity, after.request_limit, after.ai_account_limit) == (
        before.plan, before.expansion_quantity, before.request_limit, before.ai_account_limit,
    )
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT * FROM subscriptions").fetchall() == subscription
    assert len(binding_rows(database)) == 14


def test_activation_is_scoped_to_owner_even_for_shared_computer(database):
    bind_nodes(database, "other-owner", 4)
    entitlements.active_node_ids(database, "other-owner")
    with sqlite3.connect(database) as db:
        db.execute("UPDATE user_active_nodes SET manual=1 WHERE user_id='other-owner' AND node_id='node-2'")
    other_before = active_rows(database, "other-owner")
    bindings = binding_rows(database)

    entitlements.set_active_node(database, "owner", "node-2")
    entitlements.set_active_node(database, "owner", "node-0")

    assert active_rows(database, "other-owner") == other_before
    assert binding_rows(database) == bindings


@pytest.mark.parametrize("node_id", ["", "   ", "unknown", "other-only"])
def test_unbound_and_empty_activation_do_not_change_state(database, node_id):
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO user_node_bindings VALUES('other-owner','other-only',1,1)")
    before = active_rows(database)
    bindings = binding_rows(database)
    message = "Computer ID is required" if not node_id.strip() else "Computer is not connected to this account"
    with pytest.raises(ValueError, match=message):
        entitlements.set_active_node(database, "owner", node_id)
    assert active_rows(database) == before
    assert binding_rows(database) == bindings


@pytest.mark.parametrize("node_id", ["node-2", "node-0"])
def test_final_sync_failure_rolls_back_activation_and_eviction(database, monkeypatch, node_id):
    before = active_rows(database)
    bindings = binding_rows(database)
    real_sync = entitlements._sync_active
    calls = 0

    def fail_final_sync(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = real_sync(*args, **kwargs)
        if calls == 2:
            raise RuntimeError("injected final synchronization failure")
        return result

    monkeypatch.setattr(entitlements, "_sync_active", fail_final_sync)
    with pytest.raises(RuntimeError, match="injected final synchronization failure"):
        entitlements.set_active_node(database, "owner", node_id)
    assert calls == 2
    assert active_rows(database) == before
    assert binding_rows(database) == bindings


@pytest.fixture
def activation_client(tmp_path, monkeypatch, short_connections):
    # Import after isolation is applied: gateway module initialization only sees temp data.
    from gpt_windows_connector import webapp

    path = tmp_path / "activation-http.db"
    auth = AuthStore(path, "synthetic-activation-test-secret-" * 2)
    user = auth.register("activation@example.test", "synthetic-password-only")
    billing = BillingService(path, "https://activation.example.test")
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE user_node_bindings(user_id TEXT,node_id TEXT,approved_at REAL,updated_at REAL,PRIMARY KEY(user_id,node_id))")
    bind_nodes(path, user.id, 4)
    initial = entitlements.active_node_ids(path, user.id)
    monkeypatch.setattr(webapp, "gateway", SimpleNamespace(db_path=path, auth=auth, billing=billing))
    with TestClient(webapp.app) as client:
        client.headers["Authorization"] = "Bearer " + auth.issue_token(user)
        yield client, path, user.id, initial


@pytest.mark.parametrize("node_id", ["node-2", "node-0"])
def test_http_activation_and_retry_commit_before_audit_and_billing(activation_client, node_id):
    client, path, owner, initial = activation_client
    selected = None
    for _ in range(2):
        response = client.post(f"/api/nodes/{node_id}/activate")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        active = set(payload["active_node_ids"])
        assert len(active) == 3 and node_id in active
        if selected is not None:
            assert active == selected
        elif node_id in initial:
            assert active == set(initial)
        selected = active
        billing = payload["billing"]
        assert (billing["node_limit"], billing["nodes_used"], billing["nodes_connected"]) == (3, 3, 4)
        assert (billing["request_limit"], billing["ai_account_limit"]) == (100000, 3)
        assert billing["beta_free"] is True
        assert billing["billing_configured"] is False
    with sqlite3.connect(path) as db:
        audit = db.execute(
            "SELECT user_id,action,target,details FROM audit_logs ORDER BY id",
        ).fetchall()
    assert len(audit) == 2
    for user_id, action, target, details in audit:
        assert (user_id, action, target) == (owner, "node.activate", node_id)
        assert set(json.loads(details)["active_node_ids"]) == selected
    assert set(row[0] for row in active_rows(path, owner)) == selected
    assert dict((node, manual) for node, manual, _ in active_rows(path, owner))[node_id] == 1
    assert len(binding_rows(path)) == 4


def test_http_unbound_computer_returns_error_without_activation_or_audit(activation_client):
    client, path, owner, _ = activation_client
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO user_node_bindings VALUES('other-owner','other-only',1,1)")
    before = active_rows(path, owner)
    bindings = binding_rows(path)
    response = client.post("/api/nodes/other-only/activate")
    assert response.status_code == 400
    assert response.json() == {"error": "Computer is not connected to this account"}
    assert active_rows(path, owner) == before
    assert binding_rows(path) == bindings
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == 0
