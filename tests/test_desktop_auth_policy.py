"""Real HTTP/SQLite desktop adapter regressions with synthetic mail and users."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from gpt_windows_connector import gateway, login_policy, server
from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector.registration_security import RegistrationSecurity

EMAIL = 'desktop@example.test'
PASSWORD = 'synthetic-desktop-password'


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv('GWC_BYPASS_LOGIN_VERIFICATION', raising=False)
    db = tmp_path / 'gateway.db'
    auth = AuthStore(db, 'synthetic-desktop-signing-key-' * 2)
    security = RegistrationSecurity(db)
    user = auth.register(EMAIL, PASSWORD)
    monkeypatch.setattr(gateway, 'auth', auth)
    monkeypatch.setattr(gateway, 'registration_security', security)
    monkeypatch.setattr(gateway, 'settings', SimpleNamespace(public_base_url='https://lucas.example', jwt_ttl_seconds=auth.jwt_ttl_seconds))
    deliveries = []
    monkeypatch.setattr(login_policy, 'email_verification_enabled', lambda: True)
    monkeypatch.setattr(login_policy, 'send_verification_email', lambda email, code: deliveries.append((email, code)))
    return SimpleNamespace(db=db, auth=auth, security=security, user=user, mail=deliveries,
        client=TestClient(server.app, base_url='https://lucas.example'))


def start(setup, route='/auth/desktop/login'):
    return setup.client.post(route, json={'email': EMAIL, 'password': PASSWORD, 'remember': True})


def complete(setup, challenge, route='/auth/desktop/login/verify', code=None):
    return setup.client.post(route, json={'challenge_id': challenge, 'code': code or setup.mail[-1][1]})


def test_desktop_uses_shared_required_challenge_and_returns_no_cookie(setup):
    first = start(setup)
    assert first.status_code == 202 and first.json()['verification_required']
    assert 'set-cookie' not in first.headers
    response = complete(setup, first.json()['challenge_id'])
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert 'set-cookie' not in response.headers
    assert response.json()['access_token'] != 'cookie'
    assert setup.auth.verify_token(response.json()['access_token']).id == setup.user.id
    with setup.security._connect() as db:
        assert db.execute('SELECT COUNT(*) FROM trusted_login_devices').fetchone()[0] == 0
    assert complete(setup, first.json()['challenge_id']).status_code == 400


@pytest.mark.parametrize('first,wrong,right', [
    ('/auth/login', '/auth/desktop/login/verify', '/auth/login/verify'),
    ('/auth/desktop/login', '/auth/login/verify', '/auth/desktop/login/verify'),
])
def test_challenge_purpose_cannot_convert_cookie_and_bearer_flows(setup, first, wrong, right):
    challenge = start(setup, first).json()['challenge_id']
    assert complete(setup, challenge, wrong).status_code == 400
    with setup.security._connect() as db:
        row = db.execute('SELECT attempts FROM login_verifications WHERE challenge_id=?', (challenge,)).fetchone()
        assert row['attempts'] == 0
    response = complete(setup, challenge, right)
    assert response.status_code == 200
    assert (response.json()['access_token'] == 'cookie') == (right == '/auth/login/verify')


def test_rate_budget_shared_between_web_gateway_and_desktop(setup):
    clients = [setup.client, TestClient(gateway.app, base_url='https://lucas.example')]
    for attempt in range(10):
        response = clients[attempt % 2].post('/auth/login' if attempt % 3 else '/auth/desktop/login', json={'email': EMAIL, 'password': 'wrong'})
        assert response.status_code == 401
    assert start(setup).status_code == 429


def test_desktop_does_not_reuse_web_trusted_device(setup):
    challenge = start(setup, '/auth/login').json()['challenge_id']
    assert complete(setup, challenge, '/auth/login/verify').status_code == 200
    assert start(setup, '/auth/login').status_code == 200
    assert start(setup).status_code == 202


@pytest.mark.parametrize('failure', ['missing_mail', 'bad_password', 'disabled', 'expired', 'network', 'attempts'])
def test_fail_closed_without_desktop_token(setup, monkeypatch, failure):
    if failure == 'missing_mail':
        monkeypatch.setattr(login_policy, 'email_verification_enabled', lambda: False)
        response = start(setup)
    elif failure == 'bad_password':
        response = setup.client.post('/auth/desktop/login', json={'email': EMAIL, 'password': 'wrong'})
    else:
        challenge = start(setup).json()['challenge_id']
        with setup.security._connect() as db:
            if failure == 'disabled': db.execute("UPDATE users SET status='disabled'")
            elif failure == 'expired': db.execute('UPDATE login_verifications SET expires_at=0')
            elif failure == 'network': db.execute("UPDATE login_verifications SET ip_address='other'")
            elif failure == 'attempts': db.execute('UPDATE login_verifications SET attempts=5')
        response = complete(setup, challenge)
    assert response.status_code in {400, 401, 503}
    assert 'access_token' not in response.json() and 'set-cookie' not in response.headers


@pytest.mark.parametrize('suffix', ['', '/verify', '/resend'])
@pytest.mark.parametrize('body', [[], None, 'bad', 17])
def test_malformed_desktop_json_rejected(setup, suffix, body):
    response = setup.client.post('/auth/desktop/login' + suffix, json=body)
    assert response.status_code == 400


def test_resend_purpose_and_budget_shared(setup):
    challenge = start(setup).json()['challenge_id']
    data = {'challenge_id': challenge}
    assert setup.client.post('/auth/login/resend', json=data).status_code == 400
    for _ in range(5):
        assert setup.client.post('/auth/desktop/login/resend', json=data).status_code == 200
    assert setup.client.post('/auth/desktop/login/resend', json=data).status_code == 429
    assert complete(setup, challenge).status_code == 200


def test_desktop_challenge_consumption_cross_worker_atomic(setup):
    challenge = start(setup).json()['challenge_id']
    code = setup.mail[-1][1]
    def consume(_):
        try:
            return RegistrationSecurity(setup.db).verify_login(challenge, code, 'testclient', purpose='desktop')[0]
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(consume, range(4)))
    assert results.count(setup.user.id) == 1


def test_legacy_challenge_schema_migrates_as_web_without_rewriting(tmp_path):
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE login_verifications (challenge_id TEXT PRIMARY KEY,user_id TEXT,email TEXT,ip_address TEXT,remember_device INTEGER,code_hash TEXT,expires_at REAL,attempts INTEGER,created_at REAL,updated_at REAL)')
        db.execute("INSERT INTO login_verifications VALUES('old','user','a@example.test','ip',0,'hash',123,2,1,2)")
    RegistrationSecurity(path)
    RegistrationSecurity(path)
    with sqlite3.connect(path) as db:
        row = db.execute('SELECT * FROM login_verifications').fetchone()
        assert row == ('old','user','a@example.test','ip',0,'hash',123,2,1,2,'web')


def test_explicit_bypass_still_password_and_shared_policy(setup, monkeypatch):
    monkeypatch.setenv('GWC_BYPASS_LOGIN_VERIFICATION', 'true')
    response = start(setup)
    assert response.status_code == 200 and 'set-cookie' not in response.headers
    assert setup.auth.verify_token(response.json()['access_token']).id == setup.user.id
