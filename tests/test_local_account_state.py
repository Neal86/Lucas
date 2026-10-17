from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import threading
import httpx
import pytest
from gpt_windows_connector import local_account as account
from gpt_windows_connector.local_account import LocalAccountClient, normalize_account_origin
from gpt_windows_connector.local_account_state import StaleAccountOperation, atomic_write

@pytest.fixture
def vault(monkeypatch):
    values = {}

    def protect(token):
        value = f'fake-protected-{len(values)}'
        values[value] = token
        return value
    monkeypatch.setattr(account, 'protect_text', protect)
    monkeypatch.setattr(account, 'unprotect_text', lambda value: values[value])
    return values

def login_payload(user='a'):
    return {'access_token': f'synthetic-token-{user}', 'expires_in': 3600, 'user': {'id': user, 'email': f'{user}@example.test', 'name': user}}

def make_client(tmp_path, handler, origin='https://accounts.example.test'):
    return LocalAccountClient(origin, tmp_path / 'account.json', transport=httpx.MockTransport(handler))

def ok(request):
    if request.url.path == '/auth/desktop/login':
        return httpx.Response(200, json=login_payload())
    return httpx.Response(200, json={'user': {'id': 'a', 'name': 'a'}})

def signed_client(tmp_path, vault, handler=ok):
    client = make_client(tmp_path, handler)
    client.login('a@example.test', 'synthetic-password')
    return client

@pytest.mark.parametrize(('url', 'expected'), [('wss://ACCOUNTS.example.test:443/ws/node', 'https://accounts.example.test'), ('https://accounts.example.test/', 'https://accounts.example.test'), ('ws://localhost:8765/ws/node/', 'http://localhost:8765'), ('http://127.0.0.1:80', 'http://127.0.0.1'), ('http://[::1]:1234', 'http://[::1]:1234')])
def test_origin_normalization(url, expected):
    assert normalize_account_origin(url) == expected

@pytest.mark.parametrize('url', ['https://user:password@example.test', 'https://user@example.test', 'https://example.test?token=secret', 'https://example.test?', 'https://example.test#', 'https://example.test/#secret', 'https://example.test/api', 'https://example.test/ws/node/other', 'http://localhost.evil.test', 'http://127.0.0.1.evil.test', 'http://example.test', 'https://example.test:bad', 'https://example.test:65536', 'https://exa\nmple.test', 'https://example.test\\@evil.test', 'https://[::1%25zone]', 'file:///tmp/account', '', None])
def test_credential_bearing_or_ambiguous_origins_rejected(url):
    with pytest.raises(ValueError):
        normalize_account_origin(url)

def test_state_never_persists_plain_token_or_password(tmp_path, vault):
    client = signed_client(tmp_path, vault)
    text = client.state_path.read_text()
    assert 'synthetic-token' not in text and 'synthetic-password' not in text
    state = json.loads(text)
    assert state['origin'] == client.base_url
    assert state['user_id'] == 'a' and state['session_id']
    assert state['access_token_dpapi'] in vault

@pytest.mark.parametrize('body', [[], None, 'string', {'access_token': 'cookie', 'user': {'id': 'a'}}, {'access_token': 'x', 'user': []}, {'access_token': 123, 'user': {'id': 'a'}}, {'access_token': 'x', 'user': {'id': 42}}, {'access_token': 'x\r\n', 'user': {'id': 'a'}}, {'verification_required': True}, {'verification_required': True, 'challenge_id': []}])
def test_malformed_login_is_safe(tmp_path, vault, body):
    client = make_client(tmp_path, lambda req: httpx.Response(200, json=body))
    with pytest.raises((ValueError, PermissionError)):
        client.login('a@example.test', 'synthetic-password')
    assert client.status()['signed_in'] is False
    assert not client.state_path.exists()

def test_invalid_json_login_is_safe(tmp_path, vault):
    client = make_client(tmp_path, lambda req: httpx.Response(200, content=b'not-json'))
    with pytest.raises(ValueError, match='invalid response'):
        client.login('a@example.test', 'synthetic-password')
    assert client.status()['signed_in'] is False

def test_legacy_unbound_and_corrupt_state_is_not_unprotected(tmp_path, monkeypatch):
    client = make_client(tmp_path, ok)
    monkeypatch.setattr(account, 'unprotect_text', lambda _: pytest.fail('Unbound token was opened'))
    for body in (b'{"access_token_dpapi":"old","email":"private@example.test"}', b'[]', b'\xff', b'null'):
        client.state_path.write_bytes(body)
        assert client.status()['signed_in'] is False
        assert client.status()['email'] == ''
        assert client.status()['signed_in'] is False

def test_failed_protection_never_writes(tmp_path, vault, monkeypatch):
    client = make_client(tmp_path, ok)
    monkeypatch.setattr(account, 'protect_text', lambda _: (_ for _ in ()).throw(RuntimeError('fake failure')))
    with pytest.raises(RuntimeError):
        client.login('a@example.test', 'synthetic-password')
    assert not client.state_path.exists()

def test_plaintext_fallback_is_rejected(tmp_path, vault, monkeypatch):
    client = make_client(tmp_path, ok)
    monkeypatch.setattr(account, 'protect_text', lambda token: token)
    with pytest.raises(RuntimeError, match='protection'):
        client.login('a@example.test', 'synthetic-password')
    assert not client.state_path.exists()

def blocked_response(response):
    entered, release = (threading.Event(), threading.Event())

    def handle(request):
        entered.set()
        assert release.wait(5), 'Test did not release synthetic HTTP'
        return response(request) if callable(response) else response
    return (handle, entered, release)

def test_late_login_cannot_revive_logout(tmp_path, vault):
    handler, entered, release = blocked_response(httpx.Response(200, json=login_payload()))
    client = make_client(tmp_path, handler)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(client.login, 'a@example.test', 'synthetic-password')
        assert entered.wait(5)
        client.logout()
        release.set()
        with pytest.raises(StaleAccountOperation):
            future.result()
    assert client.status()['signed_in'] is False
    assert not client.state_path.exists()

def test_later_login_wins_across_clients(tmp_path, vault):
    handler, entered, release = blocked_response(httpx.Response(200, json=login_payload('a')))
    old = make_client(tmp_path, handler)
    new = make_client(tmp_path, lambda req: httpx.Response(200, json=login_payload('b')))
    with ThreadPoolExecutor() as pool:
        future = pool.submit(old.login, 'a@example.test', 'synthetic-password')
        assert entered.wait(5)
        new.login('b@example.test', 'synthetic-password')
        release.set()
        with pytest.raises(StaleAccountOperation):
            future.result()
    assert new.status()['user_id'] == 'b'

def test_redirects_never_forward_credentials(tmp_path, vault):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(307, headers={'Location': 'https://other.test/collect'})
    client = make_client(tmp_path, handler)
    with pytest.raises(PermissionError):
        client.login('a@example.test', 'synthetic-password')
    assert len(requests) == 1 and requests[0].url.host == 'accounts.example.test'

def test_cancelled_operation_does_not_dispatch_login(tmp_path, vault):
    client = make_client(tmp_path, lambda req: pytest.fail('cancelled request dispatched'))
    operation = client.new_operation()
    operation.cancel()
    with pytest.raises(StaleAccountOperation):
        client.login('a@example.test', 'synthetic-password', operation=operation)

def test_cancel_inflight_login_prevents_commit(tmp_path, vault):
    handler, entered, release = blocked_response(httpx.Response(200, json=login_payload()))
    client = make_client(tmp_path, handler)
    operation = client.new_operation()
    with ThreadPoolExecutor() as pool:
        future = pool.submit(client.login, 'a@example.test', 'synthetic-password', operation=operation)
        assert entered.wait(5)
        operation.cancel()
        release.set()
        with pytest.raises(StaleAccountOperation):
            future.result()
    assert client.status()['signed_in'] is False

def test_verification_lifecycle_contract(tmp_path, vault):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith('/verify'):
            return httpx.Response(200, json=login_payload())
        if request.url.path.endswith('/resend'):
            return httpx.Response(200, json={'ok': True})
        return httpx.Response(200, json={'verification_required': True, 'challenge_id': 'synthetic-challenge', 'email': 'a@example.test'})
    client = make_client(tmp_path, handler)
    result = client.login('a@example.test', 'synthetic-password')
    assert result['verification_required'] and (not client.status()['signed_in'])
    client.resend_login(result['challenge_id'])
    client.verify_login(result['challenge_id'], '123456')
    assert client.status()['signed_in']
    with pytest.raises(StaleAccountOperation):
        client.verify_login(result['challenge_id'], '123456')
    assert len(requests) == 3
    assert all(('Authorization' not in request.headers for request in requests))

def test_cancelled_challenge_cannot_verify(tmp_path, vault):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={'verification_required': True, 'challenge_id': 'synthetic'})
    client = make_client(tmp_path, handler)
    result = client.login('a@example.test', 'synthetic-password')
    client.cancel_pending_login(generation=result['generation'])
    with pytest.raises(StaleAccountOperation):
        client.verify_login('synthetic', '123456')
    assert len(calls) == 1

def test_late_verification_after_logout_does_not_sign_in(tmp_path, vault):
    client = make_client(tmp_path, lambda req: httpx.Response(200, json={'verification_required': True, 'challenge_id': 'synthetic'}))
    client.login('a@example.test', 'synthetic-password')
    handler, entered, release = blocked_response(httpx.Response(200, json=login_payload()))
    client._transport = httpx.MockTransport(handler)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(client.verify_login, 'synthetic', '123456')
        assert entered.wait(5)
        client.logout()
        release.set()
        with pytest.raises(StaleAccountOperation):
            future.result()
    assert not client.status()['signed_in']

def test_unique_atomic_temporary_files_under_concurrency(tmp_path, monkeypatch):
    from gpt_windows_connector import local_account_state as state
    original_replace = state.os.replace
    original_fsync = state.os.fsync
    seen = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def replace(source, dest):
        with lock:
            seen.append(str(source))
        original_replace(source, dest)

    def fsync(fd):
        original_fsync(fd)
        barrier.wait(timeout=5)

    monkeypatch.setattr(state.os, 'fsync', fsync)
    monkeypatch.setattr(state.os, 'replace', replace)
    path = tmp_path / 'atomic.json'
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: atomic_write(path, {'value': i}), range(8)))
    assert len(set(seen)) == 8
    assert json.loads(path.read_text())['value'] in range(8)
    assert list(tmp_path.glob('*.tmp')) == []


@pytest.mark.parametrize('alias_kind', ['lexical', 'relative', 'windows_case'])
def test_atomic_write_and_account_state_share_canonical_lock(tmp_path, monkeypatch, alias_kind):
    from gpt_windows_connector import local_account_state as state
    path = tmp_path / 'account.json'
    if alias_kind == 'windows_case':
        if os.name != 'nt':
            pytest.skip('Native Windows case normalization')
        alias = tmp_path / 'ACCOUNT.JSON'
    elif alias_kind == 'relative':
        monkeypatch.chdir(tmp_path)
        alias = Path('account.json')
    else:
        (tmp_path / 'nested').mkdir()
        alias = tmp_path / 'nested' / '..' / 'account.json'
    first = state.AccountState('https://accounts.example.test', path)
    second = state.AccountState('https://accounts.example.test', alias)
    assert first.shared is second.shared
    assert first.lock is state._path_lock(state._path_key(alias))

    # A real helper write must reenter the AccountState lock without deadlock.
    errors = []
    def write_while_locked():
        try:
            with first.lock:
                atomic_write(alias, {'value': 'reentrant'})
        except BaseException as error:
            errors.append(error)
    worker = threading.Thread(target=write_while_locked, daemon=True)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive(), 'atomic_write did not reuse the reentrant path lock'
    assert not errors
    assert json.loads(path.read_text()) == {'value': 'reentrant'}


def test_raw_atomic_write_does_not_initialize_account_metadata(tmp_path):
    from gpt_windows_connector import local_account_state as state
    path = tmp_path / 'raw.json'
    key = state._path_key(path)
    assert key not in state._registry
    atomic_write(path, {'value': 1})
    assert key not in state._registry
    assert key in state._path_locks


def test_same_path_atomic_replacements_are_serialized(tmp_path, monkeypatch):
    from gpt_windows_connector import local_account_state as state
    path = tmp_path / 'atomic.json'
    key = state._path_key(path)
    real_lock = state._path_lock(key)
    first_entered = threading.Event()
    second_acquiring = threading.Event()
    release = threading.Event()
    replacements = []
    original_replace = state.os.replace

    class ObservedLock:
        def __enter__(self):
            if first_entered.is_set():
                second_acquiring.set()
            real_lock.acquire()
        def __exit__(self, *args):
            real_lock.release()

    monkeypatch.setitem(state._path_locks, key, ObservedLock())
    def replace(source, dest):
        replacements.append(source)
        if len(replacements) == 1:
            first_entered.set()
            assert release.wait(5), 'First replacement was not released'
        original_replace(source, dest)
    monkeypatch.setattr(state.os, 'replace', replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(atomic_write, path, {'value': 1})
        try:
            assert first_entered.wait(5)
            second = pool.submit(atomic_write, path, {'value': 2})
            assert second_acquiring.wait(5), 'Second writer did not reach the path lock'
            assert len(replacements) == 1
        finally:
            release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    assert len(replacements) == 2
    assert json.loads(path.read_text()) == {'value': 2}
    assert list(tmp_path.glob('*.tmp')) == []


def test_different_path_atomic_replacements_are_independent(tmp_path, monkeypatch):
    from gpt_windows_connector import local_account_state as state
    first_path, second_path = tmp_path / 'first.json', tmp_path / 'second.json'
    entered, release = threading.Event(), threading.Event()
    original_replace = state.os.replace
    def replace(source, dest):
        if dest == first_path:
            entered.set()
            assert release.wait(5), 'First replacement was not released'
        original_replace(source, dest)
    monkeypatch.setattr(state.os, 'replace', replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(atomic_write, first_path, {'value': 1})
        try:
            assert entered.wait(5)
            second = pool.submit(atomic_write, second_path, {'value': 2})
            second.result(timeout=5)
            assert json.loads(second_path.read_text()) == {'value': 2}
        finally:
            release.set()
        first.result(timeout=5)
    assert json.loads(first_path.read_text()) == {'value': 1}
    assert list(tmp_path.glob('*.tmp')) == []


def test_failed_atomic_replace_propagates_and_releases_lock(tmp_path, monkeypatch):
    from gpt_windows_connector import local_account_state as state
    path = tmp_path / 'atomic.json'
    atomic_write(path, {'old': True})
    original_replace = state.os.replace
    failure = PermissionError('synthetic replacement denial')
    def fail(source, dest):
        raise failure
    monkeypatch.setattr(state.os, 'replace', fail)
    with pytest.raises(PermissionError) as caught:
        atomic_write(path, {'new': True})
    assert caught.value is failure
    assert json.loads(path.read_text()) == {'old': True}
    assert list(tmp_path.glob('*.tmp')) == []
    monkeypatch.setattr(state.os, 'replace', original_replace)
    errors = []
    def write_again():
        try:
            atomic_write(path, {'recovered': True})
        except BaseException as error:
            errors.append(error)
    worker = threading.Thread(target=write_again, daemon=True)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive(), 'Failed replacement retained the path lock'
    assert not errors
    assert json.loads(path.read_text()) == {'recovered': True}
    assert list(tmp_path.glob('*.tmp')) == []


def test_failed_atomic_serialization_keeps_previous_file_and_cleans_temp(tmp_path):
    path = tmp_path / 'atomic.json'
    atomic_write(path, {'old': True})
    with pytest.raises(ValueError):
        atomic_write(path, {'invalid': float('nan')})
    assert json.loads(path.read_text()) == {'old': True}
    assert list(tmp_path.glob('*.tmp')) == []


def test_origin_binding_and_immutable_origin(tmp_path, vault):
    a = signed_client(tmp_path, vault)
    calls = []
    b = make_client(tmp_path, lambda request: calls.append(request), 'https://other.example.test')
    assert b.status()['signed_in'] is False
    assert b.status()['email'] == ''
    with pytest.raises(PermissionError):
        b.me()
    b.logout()
    assert a.status()['signed_in'] is True
    assert calls == []
    with pytest.raises(AttributeError):
        b.base_url = a.base_url


@pytest.mark.parametrize('status', [200, 401])
def test_old_account_response_cannot_logout_replacement(tmp_path, vault, status):
    old = signed_client(tmp_path, vault)
    handler, entered, release = blocked_response(httpx.Response(status, json={'user': {'id': 'a'}}))
    old._transport = httpx.MockTransport(handler)
    new = make_client(tmp_path, lambda req: httpx.Response(200, json=login_payload('b')))
    with ThreadPoolExecutor() as pool:
        future = pool.submit(old.me)
        assert entered.wait(5)
        new.login('b@example.test', 'synthetic-password')
        release.set()
        with pytest.raises(StaleAccountOperation):
            future.result()
    assert new.status()['user_id'] == 'b'


@pytest.mark.parametrize('status', [200, 401])
def test_latest_account_request_owns_response_and_expiry(tmp_path, vault, status):
    client = signed_client(tmp_path, vault)
    handler, entered, release = blocked_response(httpx.Response(status, json={'user': {'id': 'a', 'name': 'Old'}}))
    old = make_client(tmp_path, handler)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(old.me)
        assert entered.wait(5)
        assert client.me()['name'] == 'a'
        release.set()
        with pytest.raises(StaleAccountOperation):
            future.result()
    assert client.status()['signed_in']


def test_account_response_after_logout_is_discarded(tmp_path, vault):
    client = signed_client(tmp_path, vault)
    handler, entered, release = blocked_response(httpx.Response(200, json={'user': {'id': 'a'}}))
    client._transport = httpx.MockTransport(handler)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(client.me)
        assert entered.wait(5)
        client.logout()
        release.set()
        with pytest.raises(StaleAccountOperation):
            future.result()
    assert not client.state_path.exists()


def test_current_401_signs_out(tmp_path, vault):
    client = signed_client(tmp_path, vault)
    client._transport = httpx.MockTransport(lambda req: httpx.Response(401, json={'error': 'expired'}))
    with pytest.raises(PermissionError, match='expired'):
        client.me()
    assert not client.status()['signed_in']


@pytest.mark.parametrize('body', [[], {'user': None}, {'user': []}, {'user': {'id': 'other'}}, {'user': {'id': 42}}])
def test_invalid_account_response_is_rejected(tmp_path, vault, body):
    client = signed_client(tmp_path, vault)
    client._transport = httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    with pytest.raises(ValueError):
        client.me()
    assert client.status()['signed_in']


def test_auth_only_http_contract(tmp_path, vault):
    client = signed_client(tmp_path, vault)
    requests = []
    def handler(req):
        requests.append(req)
        return httpx.Response(200, json={'user': {'id': 'a', 'email': 'a@example.test'}})
    client._transport = httpx.MockTransport(handler)
    assert client.me()['id'] == 'a'
    assert [(r.method, r.url.path) for r in requests] == [('GET', '/auth/me')]
    assert requests[0].headers['Authorization'] == 'Bearer synthetic-token-a'


def test_logout_filesystem_error_still_revokes_in_process(tmp_path, vault, monkeypatch):
    client = signed_client(tmp_path, vault)
    original = Path.unlink
    def unlink(path, *args, **kwargs):
        if path == client.state_path:
            raise OSError('synthetic removal failure')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', unlink)
    with pytest.raises(OSError, match='synthetic'):
        client.logout()
    assert not client.status()['signed_in']
    with pytest.raises(PermissionError):
        client.me()


def test_cancelled_stale_challenge_cannot_cancel_replacement(tmp_path, vault):
    client = make_client(tmp_path, lambda req: httpx.Response(200, json={'verification_required': True, 'challenge_id': 'synthetic'}))
    old = client.login('a@example.test', 'synthetic-password')
    client._transport = httpx.MockTransport(lambda req: httpx.Response(200, json=login_payload('b')))
    client.login('b@example.test', 'synthetic-password')
    client.cancel_pending_login(generation=old['generation'])
    assert client.status()['user_id'] == 'b'


def test_same_user_new_session_still_supersedes_old_request(tmp_path, vault):
    client = signed_client(tmp_path, vault)
    first_session = json.loads(client.state_path.read_text())['session_id']
    handler, entered, release = blocked_response(httpx.Response(401, json={}))
    old = make_client(tmp_path, handler)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(old.me)
        assert entered.wait(5)
        client.login('a@example.test', 'synthetic-password')
        release.set()
        with pytest.raises(StaleAccountOperation):
            future.result()
    assert client.status()['user_id'] == 'a'
    assert json.loads(client.state_path.read_text())['session_id'] != first_session


def test_verification_flag_must_be_boolean(tmp_path, vault):
    client = make_client(tmp_path, lambda req: httpx.Response(200, json={**login_payload(), 'verification_required': 'true'}))
    with pytest.raises(ValueError, match='verification response'):
        client.login('a@example.test', 'synthetic-password')
    assert not client.state_path.exists()


@pytest.mark.parametrize('ttl', [None, 0, -1, True, False, '3600', [], {}, float('inf'), float('-inf'), float('nan'), 10 ** 400])
def test_invalid_session_lifetime_is_rejected(tmp_path, vault, ttl):
    body = {**login_payload(), 'expires_in': ttl}
    # json.dumps deliberately permits synthetic non-finite values to exercise the parser.
    client = make_client(tmp_path, lambda req: httpx.Response(200, content=json.dumps(body).encode()))
    with pytest.raises(ValueError, match='session lifetime'):
        client.login('a@example.test', 'synthetic-password')
    assert not client.state_path.exists()


def test_missing_session_lifetime_is_rejected(tmp_path, vault):
    body = login_payload()
    body.pop('expires_in')
    client = make_client(tmp_path, lambda req: httpx.Response(200, json=body))
    with pytest.raises(ValueError, match='session lifetime'):
        client.login('a@example.test', 'synthetic-password')
    assert not client.state_path.exists()


def test_expiry_is_measured_conservatively_from_request_start(tmp_path, vault, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(account.time, 'time', lambda: now[0])
    def handler(req):
        now[0] = 1010.0
        return httpx.Response(200, json={**login_payload(), 'expires_in': 60})
    client = make_client(tmp_path, handler)
    client.login('a@example.test', 'synthetic-password')
    state = json.loads(client.state_path.read_text())
    assert state['issued_at'] == 1000.0 and state['expires_at'] == 1060.0
    generation = client.generation
    now[0] = 1060.0
    assert client.generation == generation + 1
    assert client.status()['signed_in'] is False
    assert client.status()['email'] == ''
    client._transport = httpx.MockTransport(lambda req: pytest.fail('expired session was dispatched'))
    with pytest.raises(PermissionError):
        client.me()


def test_response_arriving_after_its_lifetime_never_persists(tmp_path, vault, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(account.time, 'time', lambda: now[0])
    def handler(req):
        now[0] = 1061.0
        return httpx.Response(200, json={**login_payload(), 'expires_in': 60})
    client = make_client(tmp_path, handler)
    with pytest.raises(PermissionError, match='expired'):
        client.login('a@example.test', 'synthetic-password')
    assert not client.state_path.exists()


@pytest.mark.parametrize('change', [
    {'expires_at': None}, {'expires_at': 'later'}, {'expires_at': 10 ** 400},
    {'expires_at': float('nan')}, {'issued_at': True}, {'issued_at': -1},
    {'issued_at': 1000, 'expires_at': 999}, {'issued_at': 2000, 'expires_at': 3000},
    {'issued_at': 0, 'expires_at': 500},
])
def test_malformed_or_expired_persisted_lifetime_is_signed_out(tmp_path, vault, monkeypatch, change):
    monkeypatch.setattr(account.time, 'time', lambda: 1000.0)
    client = signed_client(tmp_path, vault)
    state = json.loads(client.state_path.read_text())
    client.state_path.write_text(json.dumps({**state, **change}))
    assert not client.status()['signed_in']
    with pytest.raises(PermissionError):
        client.me()


def test_clock_rollback_revokes_local_session(tmp_path, vault, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(account.time, 'time', lambda: now[0])
    client = signed_client(tmp_path, vault)
    generation = client.generation
    now[0] = 900.0
    assert client.generation == generation + 1
    assert not client.status()['signed_in']
    now[0] = 1100.0
    assert not client.status()['signed_in']


def test_same_operation_cannot_be_reused_for_concurrent_logins(tmp_path, vault):
    handler, entered, release = blocked_response(httpx.Response(200, json=login_payload()))
    client = make_client(tmp_path, handler)
    operation = client.new_operation()
    with ThreadPoolExecutor() as pool:
        first = pool.submit(client.login, 'a@example.test', 'synthetic-password', operation=operation)
        assert entered.wait(5)
        with pytest.raises(StaleAccountOperation, match='already used'):
            client.login('b@example.test', 'synthetic-password', operation=operation)
        release.set()
        assert first.result()['user_id'] == 'a'
    assert client.status()['user_id'] == 'a'
