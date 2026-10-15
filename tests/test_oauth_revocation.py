"""Real database/HTTP regressions for disconnect, rotation and grant issuance."""
from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import jwt
import pytest
from starlette.testclient import TestClient

from gpt_windows_connector import oauth, webapp
from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector.oauth import OAuthProvider
from gpt_windows_connector.server import DashboardAuthMiddleware
from test_oauth_concurrency import CHALLENGE, URI, VERIFIER, request


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("LUCAS_BETA_FREE", "1")
    path = tmp_path / "revocation.db"
    auth = AuthStore(path, "oauth-revocation-test-secret-" * 2)
    provider = OAuthProvider(path, auth, "https://lucas.example")
    user = auth.register("revocation@example.com", "test-password-123")
    with provider.db() as db:
        for cid in ("client-a", "client-b"):
            db.execute("INSERT INTO oauth_clients VALUES(?,?,?,?)", (cid, cid, json.dumps([URI]), time.time()))
    monkeypatch.setattr(webapp.gateway, "db_path", path)
    monkeypatch.setattr(webapp.gateway, "auth", auth)
    return provider, user


def disconnect(provider, user, cid="client-a"):
    with TestClient(webapp.app) as client:
        return client.delete("/api/ai-connections/" + cid,
                             headers={"Authorization": "Bearer " + provider.auth.issue_token(user)})


def redeem(provider, user, **form):
    form.setdefault("client_id", "client-a")
    return asyncio.run(provider.token(request(provider, user, form)))


def issue(provider, user, cid="client-a"):
    return provider.tokens(user, cid, "lucas offline_access", True)


def seed_code(provider, user):
    issue(provider, user)
    with provider.db() as db:
        db.execute("INSERT INTO oauth_codes VALUES(?,?,?,?,?,?,?)",
                   (provider.h("code"), "client-a", user.id, URI, "lucas", CHALLENGE, time.time() + 300))
    return {"grant_type": "authorization_code", "code": "code", "redirect_uri": URI, "code_verifier": VERIFIER}


def test_disconnect_revokes_access_and_refresh_but_keeps_web_login(setup):
    provider, user = setup
    tokens = issue(provider, user)
    web_token = provider.auth.issue_token(user)
    assert disconnect(provider, user).status_code == 200
    with pytest.raises(PermissionError):
        provider.auth.verify_token(tokens["access_token"])
    assert provider.auth.verify_token(web_token).id == user.id
    response = redeem(provider, user, grant_type="refresh_token", refresh_token=tokens["refresh_token"])
    assert response.status_code == 400 and json.loads(response.body)["error"] == "invalid_grant"


def test_reconnect_cannot_resurrect_old_access_token(setup):
    provider, user = setup
    old = issue(provider, user)
    assert disconnect(provider, user).status_code == 200
    new = issue(provider, user)
    with pytest.raises(PermissionError):
        provider.auth.verify_token(old["access_token"])
    assert provider.auth.verify_token(new["access_token"]).client_id == "client-a"


def test_disconnect_is_scoped_to_user_and_client(setup):
    provider, user = setup
    other = provider.auth.register("other@example.com", "test-password-123")
    revoked = issue(provider, user)
    other_client = issue(provider, user, "client-b")
    other_user = issue(provider, other)
    assert disconnect(provider, user).status_code == 200
    with pytest.raises(PermissionError):
        provider.auth.verify_token(revoked["access_token"])
    assert provider.auth.verify_token(other_client["access_token"]).client_id == "client-b"
    assert provider.auth.verify_token(other_user["access_token"]).id == other.id
    assert redeem(provider, other, grant_type="refresh_token", refresh_token=other_user["refresh_token"]).status_code == 200


def test_legacy_tokens_survive_upgrade_only_until_first_disconnect(setup):
    provider, user = setup
    tokens = issue(provider, user)
    payload = jwt.decode(tokens["access_token"], provider.auth.jwt_secret, algorithms=["HS256"])
    payload.pop("ogv")
    legacy = jwt.encode(payload, provider.auth.jwt_secret, algorithm="HS256")
    # Simulate the pre-upgrade database: no generation table, existing grants.
    with provider.db() as db:
        db.execute("DROP TABLE oauth_revocations")
    auth = AuthStore(provider.db_path, provider.auth.jwt_secret)
    assert auth.verify_token(legacy).id == user.id
    assert disconnect(provider, user).status_code == 200
    replacement = issue(provider, user)
    # A gateway restart/migration must not reset revocation tombstones.
    auth = AuthStore(provider.db_path, provider.auth.jwt_secret)
    OAuthProvider(provider.db_path, auth, provider.base)
    with pytest.raises(PermissionError):
        auth.verify_token(legacy)
    with pytest.raises(PermissionError):
        auth.verify_token(tokens["access_token"])
    assert auth.verify_token(replacement["access_token"]).id == user.id


def test_repeated_disconnects_never_reuse_generation(setup):
    provider, user = setup
    old = []
    for _ in range(3):
        token = issue(provider, user)["access_token"]
        old.append(token)
        assert disconnect(provider, user).status_code == 200
    current = issue(provider, user)["access_token"]
    for token in old:
        with pytest.raises(PermissionError):
            provider.auth.verify_token(token)
    assert provider.auth.verify_token(current).id == user.id


@pytest.mark.parametrize("kind", ["authorization_code", "refresh_token"])
def test_orphan_grant_cannot_restore_connection(setup, kind):
    provider, user = setup
    form = seed_code(provider, user) if kind == "authorization_code" else {
        "grant_type": kind, "refresh_token": issue(provider, user)["refresh_token"]}
    with provider.db() as db:
        db.execute("DELETE FROM oauth_client_users WHERE client_id=? AND user_id=?", ("client-a", user.id))
    response = redeem(provider, user, **form)
    assert response.status_code == 400 and json.loads(response.body)["error"] == "invalid_grant"
    with provider.db() as db:
        assert db.execute("SELECT COUNT(*) FROM oauth_client_users").fetchone()[0] == 0


def test_invalid_refresh_scope_and_client_leave_grant_untouched(setup):
    provider, user = setup
    token = issue(provider, user)["refresh_token"]
    wrong_client = redeem(provider, user, client_id="client-b", grant_type="refresh_token", refresh_token=token)
    invalid_scope = redeem(provider, user, grant_type="refresh_token", refresh_token=token, scope="admin")
    assert wrong_client.status_code == invalid_scope.status_code == 400
    assert json.loads(wrong_client.body)["error"] == "invalid_grant"
    assert json.loads(invalid_scope.body)["error"] == "invalid_scope"
    with provider.db() as db:
        assert db.execute("SELECT revoked_at FROM oauth_refresh_tokens WHERE token_hash=?", (provider.h(token),)).fetchone()[0] is None
    assert redeem(provider, user, grant_type="refresh_token", refresh_token=token, scope="lucas").status_code == 200


def test_disconnected_bearer_is_rejected_by_dashboard_http(setup):
    provider, user = setup
    tokens = issue(provider, user)
    with TestClient(DashboardAuthMiddleware(webapp.app)) as client:
        headers = {"Authorization": "Bearer " + tokens["access_token"]}
        assert client.get("/api/ai-connections", headers=headers).status_code == 200
        assert disconnect(provider, user).status_code == 200
        assert client.get("/api/ai-connections", headers=headers).status_code == 401


def test_disconnected_bearer_is_rejected_before_mcp_dispatch(setup):
    provider, user = setup
    token = issue(provider, user)["access_token"]
    assert disconnect(provider, user).status_code == 200

    async def unexpected_dispatch(scope, receive, send):
        pytest.fail("Disconnected token reached MCP dispatch")

    client = TestClient(webapp.gateway.AuthMiddleware(unexpected_dispatch))
    response = client.post("/mcp", headers={"Authorization": "Bearer " + token}, json={})
    assert response.status_code == 401
    assert "resource_metadata=" in response.headers["www-authenticate"]


def test_refresh_retry_does_not_extend_original_grace_period(setup, monkeypatch):
    provider, user = setup
    token = issue(provider, user)["refresh_token"]
    first_rotation = time.time() - 20
    with provider.db() as db:
        db.execute("UPDATE oauth_refresh_tokens SET revoked_at=? WHERE token_hash=?", (first_rotation, provider.h(token)))
    response = redeem(provider, user, grant_type="refresh_token", refresh_token=token)
    assert response.status_code == 200
    with provider.db() as db:
        assert db.execute("SELECT revoked_at FROM oauth_refresh_tokens WHERE token_hash=?", (provider.h(token),)).fetchone()[0] == first_rotation
    monkeypatch.setattr(oauth.time, "time", lambda: first_rotation + 31)
    assert redeem(provider, user, grant_type="refresh_token", refresh_token=token).status_code == 400


@pytest.mark.parametrize("kind", ["authorization_code", "refresh_token"])
def test_disconnect_wins_over_inflight_grant_issuance(setup, monkeypatch, kind):
    provider, user = setup
    form = seed_code(provider, user) if kind == "authorization_code" else {
        "grant_type": kind, "refresh_token": issue(provider, user)["refresh_token"]}
    reached, release, deleting = threading.Event(), threading.Event(), threading.Event()
    real = provider.tokens

    def paused(*args, **kwargs):
        reached.set()
        assert release.wait(10)
        return real(*args, **kwargs)

    def delete():
        deleting.set()
        return disconnect(provider, user)

    monkeypatch.setattr(provider, "tokens", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        exchange = pool.submit(redeem, provider, user, **form)
        assert reached.wait(10)
        removal = pool.submit(delete)
        assert deleting.wait(10)
        time.sleep(0.1)
        release.set()
        response, deleted = exchange.result(10), removal.result(10)
    assert deleted.status_code == 200 and response.status_code == 200
    with provider.db() as db:
        for table in ("oauth_client_users", "oauth_refresh_tokens", "oauth_codes"):
            assert db.execute(f"SELECT COUNT(*) FROM {table} WHERE client_id=? AND user_id=?", ("client-a", user.id)).fetchone()[0] == 0
    with pytest.raises(PermissionError):
        provider.auth.verify_token(json.loads(response.body)["access_token"])


@pytest.mark.parametrize("kind", ["authorization_code", "refresh_token"])
def test_failed_token_issuance_keeps_grant_retryable(setup, monkeypatch, kind):
    provider, user = setup
    form = seed_code(provider, user) if kind == "authorization_code" else {
        "grant_type": kind, "refresh_token": issue(provider, user)["refresh_token"]}
    real = provider.tokens

    def fail(*args, **kwargs):
        raise RuntimeError("simulated token signing failure")

    monkeypatch.setattr(provider, "tokens", fail)
    with pytest.raises(RuntimeError, match="simulated"):
        redeem(provider, user, **form)
    with provider.db() as db:
        if kind == "authorization_code":
            assert db.execute("SELECT COUNT(*) FROM oauth_codes WHERE code_hash=?", (provider.h("code"),)).fetchone()[0] == 1
        else:
            assert db.execute("SELECT revoked_at FROM oauth_refresh_tokens WHERE token_hash=?", (provider.h(form["refresh_token"]),)).fetchone()[0] is None
    monkeypatch.setattr(provider, "tokens", real)
    assert redeem(provider, user, **form).status_code == 200


def test_signing_failure_rolls_back_inserted_replacement_refresh(setup, monkeypatch):
    provider, user = setup
    form = seed_code(provider, user)
    with provider.db() as db:
        before = db.execute("SELECT COUNT(*) FROM oauth_refresh_tokens").fetchone()[0]
    real = provider.auth.issue_token

    def fail_oauth(*args, **kwargs):
        if kwargs.get("client_id"):
            raise RuntimeError("simulated signing failure")
        return real(*args, **kwargs)

    monkeypatch.setattr(provider.auth, "issue_token", fail_oauth)
    with pytest.raises(RuntimeError, match="signing failure"):
        redeem(provider, user, **form)
    with provider.db() as db:
        assert db.execute("SELECT COUNT(*) FROM oauth_refresh_tokens").fetchone()[0] == before
        assert db.execute("SELECT COUNT(*) FROM oauth_codes").fetchone()[0] == 1
