"""Shared password-login policy and safe OAuth continuation, with synthetic mail."""
import json
import time
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from gpt_windows_connector import gateway, server
from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector.oauth import OAuthProvider
from gpt_windows_connector.registration_security import RegistrationSecurity


EMAIL = "login@example.com"
PASSWORD = "synthetic-test-password-123"
URI = "https://client.example/callback?kept=1"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv("GWC_BYPASS_LOGIN_VERIFICATION", raising=False)
    monkeypatch.delenv("GWC_SMTP_HOST", raising=False)
    monkeypatch.delenv("GWC_SMTP_FROM", raising=False)
    path = tmp_path / "login.db"
    auth = AuthStore(path, "shared-login-policy-test-secret-" * 2)
    security = RegistrationSecurity(path)
    provider = OAuthProvider(path, auth, "https://lucas.example")
    user = auth.register(EMAIL, PASSWORD)
    monkeypatch.setattr(gateway, "auth", auth)
    monkeypatch.setattr(gateway, "registration_security", security)
    monkeypatch.setattr(gateway, "settings", SimpleNamespace(public_base_url="https://lucas.example", jwt_ttl_seconds=auth.jwt_ttl_seconds))
    with provider.db() as db:
        db.execute("INSERT INTO oauth_clients VALUES(?,?,?,?)", ("client", "Test Client", json.dumps([URI]), time.time()))
        db.execute("INSERT INTO oauth_requests VALUES(?,?,?,?,?,?,?)", ("request-id", "client", URI, "original-state", "lucas", "challenge", time.time() + 600))
    routes = [Route("/auth/login", server.secure_auth_login, methods=["POST"]),
              Route("/gateway/auth/login", gateway.auth_login, methods=["POST"]),
              Route("/auth/login/verify", gateway.auth_login_verify, methods=["POST"]),
              Route("/auth/login/resend", gateway.auth_login_resend, methods=["POST"]),
              Route("/oauth/authorize/resume", provider.authorize_resume, methods=["GET"]),
              Route("/oauth/authorize/cancel", provider.authorize_cancel, methods=["POST"]),
              Route("/oauth/authorize/login", provider.authorize_login, methods=["POST"])]
    return SimpleNamespace(auth=auth, security=security, provider=provider, user=user,
                           client=TestClient(Starlette(routes=routes), base_url="https://lucas.example"))


def test_oauth_password_post_cannot_bypass_required_email_verification(setup):
    response = setup.client.post("/oauth/authorize/login", data={"request_id": "request-id", "email": EMAIL, "password": PASSWORD})
    assert "gwc_access_token" not in response.cookies
    assert "gwc_access_token" not in response.headers.get("set-cookie", "")


def test_standalone_gateway_also_fails_closed_without_mail(setup):
    response = setup.client.post("/gateway/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 503
    assert "gwc_access_token" not in response.cookies


def test_web_and_gateway_login_share_attempt_limit(setup):
    for attempt in range(10):
        path = "/auth/login" if attempt % 2 else "/gateway/auth/login"
        response = setup.client.post(path, json={"email": EMAIL, "password": "wrong"})
        assert response.status_code == 401
    response = setup.client.post("/gateway/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 429
    assert "gwc_access_token" not in response.cookies


@pytest.fixture
def mail(monkeypatch):
    from gpt_windows_connector import login_policy
    deliveries = []
    monkeypatch.setattr(login_policy, "email_verification_enabled", lambda: True)
    monkeypatch.setattr(login_policy, "send_verification_email", lambda email, code: deliveries.append((email, code)))
    return deliveries


def start(setup, remember=True, path="/auth/login", ip="192.0.2.1"):
    return setup.client.post(path, json={"email": EMAIL, "password": PASSWORD, "remember": remember}, headers={"cf-connecting-ip": ip})


def verify(setup, challenge, code, ip="192.0.2.1"):
    return setup.client.post("/auth/login/verify", json={"challenge_id": challenge, "code": code}, headers={"cf-connecting-ip": ip})


def grant_counts(setup):
    with setup.provider.db() as db:
        return [db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("oauth_codes", "oauth_client_users", "oauth_refresh_tokens")]


@pytest.mark.parametrize("path", ["/auth/login", "/gateway/auth/login"])
def test_verified_cookie_requires_code_on_every_login_route(setup, mail, path):
    response = start(setup, path=path)
    assert response.status_code == 202
    assert "gwc_access_token" not in response.cookies
    assert mail[0][0] == EMAIL
    challenge = response.json()["challenge_id"]
    wrong = "000000" if mail[0][1] != "000000" else "111111"
    assert verify(setup, challenge, wrong).status_code == 400
    assert "gwc_access_token" not in setup.client.cookies
    response = verify(setup, challenge, mail[0][1])
    assert response.status_code == 200
    assert response.json()["access_token"] == "cookie"
    assert setup.auth.verify_token(response.cookies["gwc_access_token"]).id == setup.user.id
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert "gwc_trusted_login_device" in response.cookies
    assert verify(setup, challenge, mail[0][1]).status_code == 400
    assert grant_counts(setup) == [0, 0, 0]


def test_remembered_device_requires_same_network_and_password(setup, mail):
    challenge = start(setup).json()["challenge_id"]
    assert verify(setup, challenge, mail[-1][1]).status_code == 200
    setup.client.cookies.delete("gwc_access_token")
    assert start(setup, path="/gateway/auth/login").status_code == 200
    assert len(mail) == 1
    setup.client.cookies.delete("gwc_access_token")
    changed = start(setup, ip="192.0.2.2")
    assert changed.status_code == 202
    assert "gwc_access_token" not in setup.client.cookies
    assert len(mail) == 2
    assert start(setup).status_code == 202  # Changed network invalidated trust.


def test_unchecked_remember_always_verifies_and_clears_trusted_cookie(setup, mail):
    challenge = start(setup, remember=False).json()["challenge_id"]
    response = verify(setup, challenge, mail[-1][1])
    assert response.status_code == 200
    assert "gwc_trusted_login_device" not in setup.client.cookies
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert start(setup, remember=False).status_code == 202


@pytest.mark.parametrize("failure", ["expired", "network", "attempts", "disabled"])
def test_verification_failure_never_issues_cookie(setup, mail, failure):
    challenge = start(setup).json()["challenge_id"]
    with setup.provider.db() as db:
        if failure == "expired":
            db.execute("UPDATE login_verifications SET expires_at=0 WHERE challenge_id=?", (challenge,))
        elif failure == "attempts":
            db.execute("UPDATE login_verifications SET attempts=5 WHERE challenge_id=?", (challenge,))
        elif failure == "disabled":
            db.execute("UPDATE users SET status='disabled' WHERE id=?", (setup.user.id,))
    response = verify(setup, challenge, mail[-1][1], ip="192.0.2.2" if failure == "network" else "192.0.2.1")
    assert response.status_code == (401 if failure == "disabled" else 400)
    assert "gwc_access_token" not in response.cookies


def test_resend_rotates_code_and_has_shared_limit(setup, mail):
    challenge = start(setup).json()["challenge_id"]
    old = mail[-1][1]
    # Deterministically avoid the legitimate one-in-a-million code collision.
    import gpt_windows_connector.registration_security as registration
    from unittest.mock import patch
    replacement = (int(old) + 1) % 1_000_000
    with patch.object(registration.secrets, "randbelow", return_value=replacement):
        response = setup.client.post("/auth/login/resend", json={"challenge_id": challenge}, headers={"cf-connecting-ip": "192.0.2.1"})
    assert response.status_code == 200
    assert verify(setup, challenge, old).status_code == 400
    for _ in range(5):
        assert setup.client.post("/auth/login/resend", json={"challenge_id": challenge}, headers={"cf-connecting-ip": "192.0.2.1"}).status_code == 200
    assert setup.client.post("/auth/login/resend", json={"challenge_id": challenge}, headers={"cf-connecting-ip": "192.0.2.1"}).status_code == 429
    assert verify(setup, challenge, mail[-1][1]).status_code == 200


def test_explicit_setup_bypass_still_obeys_password_and_rate_policy(setup, monkeypatch):
    monkeypatch.setenv("GWC_BYPASS_LOGIN_VERIFICATION", "true")
    response = start(setup, path="/gateway/auth/login")
    assert response.status_code == 200
    assert "gwc_access_token" in response.cookies
    with setup.provider.db() as db:
        assert db.execute("SELECT action FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()[0] == "auth.login_staging_bypass"
    assert setup.client.post("/auth/login", json={"email": EMAIL, "password": "wrong"}).status_code == 401


def test_legacy_oauth_post_never_checks_or_echoes_password(setup, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Legacy OAuth must not authenticate")
    monkeypatch.setattr(setup.auth, "login", forbidden)
    response = setup.client.post("/oauth/authorize/login", data={"request_id": "request-id", "email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    assert PASSWORD not in response.text and EMAIL not in response.text
    assert 'id="loginForm"' in response.text
    assert response.headers["cache-control"] == "no-store"
    assert grant_counts(setup) == [0, 0, 0]


def test_resume_requires_cookie_and_keeps_consent_explicit(setup, mail):
    response = setup.client.get("/oauth/authorize/resume?request_id=request-id&return_to=https://evil.example")
    assert response.status_code == 200 and 'id="loginForm"' in response.text
    challenge = start(setup).json()["challenge_id"]
    verify(setup, challenge, mail[-1][1])
    response = setup.client.get("/oauth/authorize/resume?request_id=request-id&return_to=https://evil.example")
    assert response.status_code == 200
    assert "Connect Test Client?" in response.text
    assert "https://evil.example" not in response.text
    assert grant_counts(setup) == [0, 0, 0]
    assert setup.provider.req("request-id") is not None


def test_cancel_before_login_uses_only_stored_destination_and_is_one_use(setup):
    from urllib.parse import urlsplit, parse_qs
    response = setup.client.post("/oauth/authorize/cancel", data={"request_id": "request-id", "redirect_uri": "https://evil.example", "state": "evil"}, follow_redirects=False)
    assert response.status_code == 302
    target = urlsplit(response.headers["location"])
    assert (target.scheme, target.netloc, target.path) == ("https", "client.example", "/callback")
    assert parse_qs(target.query) == {"kept": ["1"], "error": ["access_denied"], "state": ["original-state"]}
    assert setup.provider.req("request-id") is None
    assert grant_counts(setup) == [0, 0, 0]
    assert setup.client.post("/oauth/authorize/cancel", data={"request_id": "request-id"}).status_code == 400


@pytest.mark.parametrize("route", ["login", "resume", "cancel"])
@pytest.mark.parametrize("request_id", ["unknown", "request-id"])
def test_unknown_or_expired_oauth_continuation_fails_locally(setup, route, request_id):
    with setup.provider.db() as db:
        db.execute("UPDATE oauth_requests SET expires_at=0")
    if route == "resume":
        response = setup.client.get(f"/oauth/authorize/{route}", params={"request_id": request_id})
    else:
        response = setup.client.post(f"/oauth/authorize/{route}", data={"request_id": request_id}, follow_redirects=False)
    assert response.status_code == 400
    assert "location" not in response.headers
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("path", ["/auth/login", "/auth/login/verify", "/auth/login/resend"])
def test_malformed_json_object_is_rejected(setup, path):
    assert setup.client.post(path, json=[]).status_code == 400
    assert setup.client.post(path, content="not json", headers={"content-type": "application/json"}).status_code == 400


def test_actual_gateway_exposes_shared_verification_routes_without_auth(setup, mail):
    client = TestClient(gateway.app, base_url="https://lucas.example")
    response = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 202
    challenge = response.json()["challenge_id"]
    assert client.post("/auth/login/resend", json={"challenge_id": challenge}).status_code == 200
    assert client.post("/auth/login/verify", json={"challenge_id": challenge, "code": mail[-1][1]}).status_code == 200


def test_existing_access_tokens_remain_valid(setup):
    token = setup.auth.issue_token(setup.user)
    assert setup.auth.verify_token(token).id == setup.user.id
    setup.client.cookies.set("gwc_access_token", token)
    response = setup.client.get("/oauth/authorize/resume?request_id=request-id")
    assert "Connect Test Client?" in response.text
    assert grant_counts(setup) == [0, 0, 0]


def test_dashboard_login_verification_runtime_initializes_and_clears_state():
    """Exercise the composed runtime rather than matching one-line functions."""
    from test_dashboard_auth_modes import run_dashboard_js

    run_dashboard_js("""
await beginChallenge();
assert.equal(loginResendBtn.disabled,true);
assert.equal(intervals.size,1);
loginVerifyCode.value='123456';
cancelLoginVerification();
assertMode('loginForm');assertReset();
""")
