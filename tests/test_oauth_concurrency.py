"""Exercise OAuth handlers against real SQLite connections in parallel workers."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

import pytest
from starlette.requests import Request

from gpt_windows_connector import oauth
from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector.entitlements import ensure_ai_capacity, snapshot
from gpt_windows_connector.oauth import OAuthProvider


URI = "https://client.example/callback"
VERIFIER = "a-valid-pkce-verifier-with-at-least-forty-three-characters"
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("LUCAS_BETA_FREE", "1")
    path = tmp_path / "oauth.db"
    auth = AuthStore(path, "oauth-concurrency-test-secret-" * 2)
    user = auth.register("concurrency@example.com", "test-password-123")
    provider = OAuthProvider(path, auth, "https://lucas.example")
    with provider.db() as db:
        for cid in ("old-a", "old-b", "new-a", "new-b"):
            db.execute("INSERT INTO oauth_clients VALUES(?,?,?,?)", (cid, cid, json.dumps([URI]), time.time()))
    snapshot(path, user.id)
    return provider, user


def request(provider, user, form):
    body = urlencode(form).encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    cookie = "gwc_access_token=" + provider.auth.issue_token(user)
    return Request({"type": "http", "method": "POST", "path": "/oauth", "headers": [
        (b"content-type", b"application/x-www-form-urlencoded"), (b"cookie", cookie.encode())
    ]}, receive)


def parallel(*calls):
    start = threading.Barrier(len(calls))

    def run(call):
        start.wait(timeout=10)
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(run, calls))


def count(provider, table):
    assert table in {"oauth_codes", "oauth_requests", "oauth_client_users", "oauth_refresh_tokens"}
    with provider.db() as db:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def seed_request(provider, cid, rid):
    with provider.db() as db:
        db.execute("INSERT INTO oauth_requests VALUES(?,?,?,?,?,?,?)",
                   (rid, cid, URI, "retained-state", "lucas offline_access", CHALLENGE, time.time() + 600))


def consent(provider, user, rid, decision="allow"):
    return asyncio.run(provider.authorize_decision(request(provider, user, {"request_id": rid, "decision": decision})))


def seed_code(provider, user):
    provider.refresh("new-a", user.id, "lucas")
    with provider.db() as db:
        db.execute("INSERT INTO oauth_codes VALUES(?,?,?,?,?,?,?)",
                   (provider.h("one-use-code"), "new-a", user.id, URI, "lucas", CHALLENGE, time.time() + 300))


def exchange(provider, user, **changes):
    form = {"grant_type": "authorization_code", "client_id": "new-a", "redirect_uri": URI,
            "code": "one-use-code", "code_verifier": VERIFIER}
    form.update(changes)
    return asyncio.run(provider.token(request(provider, user, form)))


def slow_capacity(monkeypatch):
    real = oauth.ensure_ai_capacity

    def delayed(*args, **kwargs):
        result = real(*args, **kwargs)
        # Force meaningful overlap at the formerly unprotected check/write gap.
        # With the fix this delay remains inside the SQLite write transaction.
        time.sleep(0.1)
        return result

    monkeypatch.setattr(oauth, "ensure_ai_capacity", delayed)


def test_parallel_refresh_admission_cannot_exceed_beta_limit(setup, monkeypatch):
    provider, user = setup
    for cid in ("old-a", "old-b"):
        provider.refresh(cid, user.id, "lucas")
    slow_capacity(monkeypatch)

    def attempt(cid):
        try:
            provider.refresh(cid, user.id, "lucas")
            return "accepted"
        except PermissionError:
            return "limited"

    assert sorted(parallel(lambda: attempt("new-a"), lambda: attempt("new-b"))) == ["accepted", "limited"]
    assert snapshot(provider.db_path, user.id).ai_accounts_used == 3
    assert count(provider, "oauth_refresh_tokens") == 3


def test_parallel_consent_admission_cannot_exceed_beta_limit(setup, monkeypatch):
    provider, user = setup
    for cid in ("old-a", "old-b"):
        provider.refresh(cid, user.id, "lucas")
    seed_request(provider, "new-a", "request-a")
    seed_request(provider, "new-b", "request-b")
    slow_capacity(monkeypatch)
    responses = parallel(lambda: consent(provider, user, "request-a"), lambda: consent(provider, user, "request-b"))
    assert sorted(r.status_code for r in responses) == [302, 403]
    assert snapshot(provider.db_path, user.id).ai_accounts_used == 3
    assert count(provider, "oauth_codes") == 1
    assert count(provider, "oauth_requests") == 1  # Limited consent can be retried after disconnecting an account.


def test_duplicate_consent_creates_exactly_one_code(setup, monkeypatch):
    provider, user = setup
    seed_request(provider, "new-a", "same-request")
    real = provider.req
    read = threading.Barrier(2)

    def overlap(rid):
        result = real(rid)
        read.wait(timeout=10)
        return result

    monkeypatch.setattr(provider, "req", overlap)
    responses = parallel(lambda: consent(provider, user, "same-request"), lambda: consent(provider, user, "same-request"))
    assert sorted(r.status_code for r in responses) == [302, 400]
    assert count(provider, "oauth_codes") == 1
    assert count(provider, "oauth_client_users") == 1
    assert count(provider, "oauth_requests") == 0
    redirect = next(r for r in responses if r.status_code == 302)
    assert "state=retained-state" in redirect.headers["location"]


def test_parallel_code_exchange_is_one_use(setup, monkeypatch):
    provider, user = setup
    seed_code(provider, user)
    real = provider.pkce

    def overlap(verifier, challenge):
        valid = real(verifier, challenge)
        time.sleep(0.1)
        return valid

    monkeypatch.setattr(provider, "pkce", overlap)
    before = count(provider, "oauth_refresh_tokens")
    responses = parallel(lambda: exchange(provider, user), lambda: exchange(provider, user))
    assert sorted(r.status_code for r in responses) == [200, 400]
    assert count(provider, "oauth_codes") == 0
    assert count(provider, "oauth_refresh_tokens") == before + 1
    success = next(r for r in responses if r.status_code == 200)
    assert success.headers["cache-control"] == "no-store"
    assert provider.auth.verify_token(json.loads(success.body)["access_token"]).client_id == "new-a"
    assert json.loads(next(r for r in responses if r.status_code == 400).body)["error"] == "invalid_grant"


@pytest.mark.parametrize("changes", [{"code_verifier": "wrong"}, {"client_id": "new-b"}, {"redirect_uri": URI + "/wrong"}])
def test_invalid_exchange_does_not_consume_valid_code(setup, changes):
    provider, user = setup
    seed_code(provider, user)
    assert exchange(provider, user, **changes).status_code == 400
    assert count(provider, "oauth_codes") == 1
    assert exchange(provider, user).status_code == 200
    assert exchange(provider, user).status_code == 400


def test_existing_client_can_renew_at_limit(setup):
    provider, user = setup
    for cid in ("old-a", "old-b", "new-a"):
        provider.refresh(cid, user.id, "lucas")
    provider.refresh("new-a", user.id, "lucas")
    seed_request(provider, "new-a", "reconnect")
    assert consent(provider, user, "reconnect").status_code == 302
    assert snapshot(provider.db_path, user.id).ai_accounts_used == 3


def test_denied_consent_consumes_request_without_account_or_code(setup):
    provider, user = setup
    seed_request(provider, "new-a", "deny-request")
    response = consent(provider, user, "deny-request", "deny")
    assert response.status_code == 302 and "error=access_denied" in response.headers["location"]
    assert consent(provider, user, "deny-request").status_code == 400
    assert count(provider, "oauth_client_users") == count(provider, "oauth_codes") == 0


@pytest.mark.parametrize("table,call", [("oauth_codes", "consent"), ("oauth_refresh_tokens", "refresh")])
def test_failed_grant_insert_rolls_back_account_admission(setup, table, call):
    provider, user = setup
    seed_request(provider, "new-a", "retryable")
    with provider.db() as db:
        db.execute(f"CREATE TRIGGER fail_grant BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="test failure"):
        if call == "consent":
            consent(provider, user, "retryable")
        else:
            provider.refresh("new-a", user.id, "lucas")
    assert count(provider, "oauth_client_users") == 0
    assert count(provider, "oauth_requests") == 1
    assert count(provider, table) == 0


def test_entitlement_helpers_preserve_caller_transaction(setup):
    provider, user = setup
    with provider.db() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO oauth_client_users VALUES(?,?,?)", ("new-a", user.id, time.time()))
        assert ensure_ai_capacity(provider.db_path, user.id, "new-a", connection=db).ai_accounts_used == 1
        assert db.in_transaction
        # A separate connection must not see the uncommitted admission.
        assert count(provider, "oauth_client_users") == 0
        db.rollback()
    assert count(provider, "oauth_client_users") == 0


def test_atomic_admission_honors_admin_bonus_and_expiry(setup):
    provider, user = setup
    with provider.db() as db:
        db.execute("INSERT INTO entitlement_overrides(user_id,bonus_ai_accounts,expires_at) VALUES(?,?,?)", (user.id, 1, time.time() + 60))
    for cid in ("old-a", "old-b", "new-a", "new-b"):
        provider.refresh(cid, user.id, "lucas")
    assert snapshot(provider.db_path, user.id).ai_accounts_used == 4
    with provider.db() as db:
        db.execute("UPDATE entitlement_overrides SET expires_at=?", (time.time() - 1,))
    provider.refresh("new-b", user.id, "lucas")  # Existing connections survive a bonus expiry.
    with pytest.raises(PermissionError):
        provider.refresh("fifth-client", user.id, "lucas")


def test_parallel_allow_and_deny_consumes_consent_once(setup, monkeypatch):
    provider, user = setup
    seed_request(provider, "new-a", "mixed-request")
    real = provider.req
    read = threading.Barrier(2)

    def overlap(rid):
        result = real(rid)
        read.wait(timeout=10)
        return result

    monkeypatch.setattr(provider, "req", overlap)
    responses = parallel(lambda: consent(provider, user, "mixed-request", "allow"),
                         lambda: consent(provider, user, "mixed-request", "deny"))
    assert sorted(r.status_code for r in responses) == [302, 400]
    redirect = next(r for r in responses if r.status_code == 302)
    allowed = "code=" in redirect.headers["location"]
    assert count(provider, "oauth_codes") == int(allowed)
    assert count(provider, "oauth_client_users") == int(allowed)
    assert count(provider, "oauth_requests") == 0


def test_capacity_error_does_not_commit_caller_transaction(setup):
    provider, user = setup
    for cid in ("old-a", "old-b", "new-a"):
        provider.refresh(cid, user.id, "lucas")
    with provider.db() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO oauth_requests VALUES(?,?,?,?,?,?,?)",
                   ("uncommitted", "new-b", URI, "state", "lucas", CHALLENGE, time.time() + 60))
        with pytest.raises(PermissionError):
            ensure_ai_capacity(provider.db_path, user.id, "new-b", connection=db)
        assert db.in_transaction
        assert count(provider, "oauth_requests") == 0
        db.rollback()
    assert count(provider, "oauth_requests") == 0
