import sqlite3
from types import SimpleNamespace

from gpt_windows_connector.gateway_readiness import critical_ready, readiness_checks


class _Billing:
    checkout_configured = True
    annual_checkout_configured = True
    webhook_configured = True


def _settings():
    return SimpleNamespace(
        jwt_secret="test-secret",
        google_client_id="google-id",
        google_client_secret="google-secret",
    )


def test_readiness_accepts_persisted_super_admin_without_env(tmp_path, monkeypatch):
    monkeypatch.delenv("GWC_SUPER_ADMIN_EMAIL", raising=False)
    db_path = tmp_path / "gateway.db"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE users(id TEXT PRIMARY KEY, role TEXT)")
        db.execute("INSERT INTO users VALUES('admin-1','super_admin')")

    checks = readiness_checks(db_path, _settings(), _Billing(), lambda: True)
    assert checks["database"] is True
    assert checks["super_admin_configured"] is True
    assert critical_ready(checks) is True


def test_readiness_requires_super_admin_when_env_and_db_are_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("GWC_SUPER_ADMIN_EMAIL", raising=False)
    db_path = tmp_path / "gateway.db"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE users(id TEXT PRIMARY KEY, role TEXT)")

    checks = readiness_checks(db_path, _settings(), _Billing(), lambda: True)
    assert checks["super_admin_configured"] is False
    assert critical_ready(checks) is False
