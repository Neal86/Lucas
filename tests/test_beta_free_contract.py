from __future__ import annotations

import sqlite3

from gpt_windows_connector.entitlements import beta_free_enabled, snapshot, ensure_request_capacity


def test_beta_flag_defaults_on(monkeypatch):
    monkeypatch.delenv("LUCAS_BETA_FREE", raising=False)
    assert beta_free_enabled()


def test_beta_flag_can_be_disabled(monkeypatch):
    monkeypatch.setenv("LUCAS_BETA_FREE", "false")
    assert not beta_free_enabled()


def test_beta_preserves_paid_subscription_but_uses_free_entitlements(tmp_path, monkeypatch):
    monkeypatch.setenv("LUCAS_BETA_FREE", "1")
    db_path = tmp_path / "lucas.db"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE subscriptions (user_id TEXT PRIMARY KEY, plan TEXT, status TEXT, expansion_quantity INTEGER, bonus_requests INTEGER, current_period_start REAL, current_period_end REAL, cancel_at_period_end INTEGER)")
        db.execute("INSERT INTO subscriptions VALUES ('user-1','pro','active',0,0,0,0,0)")
        db.execute("CREATE TABLE oauth_client_users (user_id TEXT, client_id TEXT)")
        db.execute("CREATE TABLE user_node_bindings (user_id TEXT, node_id TEXT, approved_at REAL)")
    ent = snapshot(db_path, "user-1")
    assert ent.plan == "free"
    assert ent.plan_name == "Lucas Beta"
    assert ent.request_limit == 100_000
    assert ent.node_limit == 3
    assert ent.ai_account_limit == 3
    assert not ent.can_buy_expansion
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT plan,status FROM subscriptions WHERE user_id='user-1'").fetchone() == ("pro", "active")
