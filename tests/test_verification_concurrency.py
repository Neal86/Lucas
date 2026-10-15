"""One-use email challenges across independent real SQLite workers."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import threading
from types import SimpleNamespace

import pytest

from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector import registration_security as registration
from gpt_windows_connector.registration_security import RegistrationSecurity


IP = "192.0.2.10"
EMAIL = "verification@example.test"
PASSWORD = "synthetic-verification-password"


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "verification.db"
    auth = AuthStore(path, "synthetic-verification-signing-secret-" * 2)
    return auth, RegistrationSecurity(path), RegistrationSecurity(path)


def ordered_overlap(monkeypatch, second, first_call, second_call,
                    *, first_at="compare", second_at="compare"):
    """Hold the first worker after its read until the second worker contends.

    Fixed code signals from SQLite's BEGIN trace, before waiting on the writer
    lock. Old code has no explicit BEGIN and instead signals after its stale
    read, at comparison/code generation. Both paths use events, never sleeps.
    """
    first_ready, contender_ready = threading.Event(), threading.Event()
    worker = threading.local()
    real_connect = second._connect
    real_compare = registration.secrets.compare_digest
    real_randbelow = registration.secrets.randbelow

    def trace(sql):
        if sql.strip().upper() == "BEGIN IMMEDIATE":
            contender_ready.set()

    def connect():
        db = real_connect()
        db.set_trace_callback(trace)
        return db

    def checkpoint(operation):
        role = getattr(worker, "role", None)
        if role == "first" and operation == first_at:
            first_ready.set()
            assert contender_ready.wait(10), "Second worker never reached its lock/read boundary"
        elif role == "second" and operation == second_at:
            contender_ready.set()

    def compare(*args):
        checkpoint("compare")
        return real_compare(*args)

    def randbelow(limit):
        checkpoint("generate")
        return real_randbelow(limit)

    def run(role, call):
        worker.role = role
        try:
            return call()
        except ValueError as exc:
            return str(exc)

    monkeypatch.setattr(second, "_connect", connect)
    monkeypatch.setattr(registration.secrets, "compare_digest", compare)
    monkeypatch.setattr(registration.secrets, "randbelow", randbelow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_result = pool.submit(run, "first", first_call)
        try:
            assert first_ready.wait(10), "First worker never reached its read/check boundary"
            second_result = pool.submit(run, "second", second_call)
            return [first_result.result(timeout=10), second_result.result(timeout=10)]
        finally:
            contender_ready.set()


def login_challenge(setup, remember=True):
    auth, first, second = setup
    user = auth.register(EMAIL, PASSWORD)
    challenge, code = first.start_login_verification(user.id, EMAIL, IP, remember)
    return user, challenge, code


@pytest.mark.parametrize("remember", [False, True])
def test_login_code_is_one_use_across_instances(setup, monkeypatch, remember):
    auth, first, second = setup
    user, challenge, code = login_challenge(setup, remember)
    results = ordered_overlap(monkeypatch, second,
                              lambda: first.verify_login(challenge, code, IP),
                              lambda: second.verify_login(challenge, code, IP))
    accepted = [result for result in results if isinstance(result, tuple)]
    assert len(accepted) == 1, results
    assert accepted[0][:2] == (user.id, remember)
    assert "Login verification session expired" in results
    with auth._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM login_verifications").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM trusted_login_devices").fetchone()[0] == int(remember)


def test_registration_code_is_one_use_across_instances(setup, monkeypatch):
    auth, first, second = setup
    email, code = first.start(EMAIL, PASSWORD)
    results = ordered_overlap(monkeypatch, second,
                              lambda: first.verify(email, code),
                              lambda: second.verify(email, code))
    assert results.count("No pending verification for this email") == 1, results
    with auth._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM pending_registrations").fetchone()[0] == 0


@pytest.mark.parametrize("kind", ["login", "registration"])
def test_concurrent_bad_attempts_cannot_exceed_limit(setup, monkeypatch, kind):
    auth, first, second = setup
    if kind == "login":
        _, key, code = login_challenge(setup)
        table, column = "login_verifications", "challenge_id"
        verify = lambda instance, value: instance.verify_login(key, value, IP)
    else:
        key, code = first.start(EMAIL, PASSWORD)
        table, column = "pending_registrations", "email"
        verify = lambda instance, value: instance.verify(key, value)
    with auth._connect() as db:
        db.execute(f"UPDATE {table} SET attempts=4 WHERE {column}=?", (key,))
    bad = "000000" if code != "000000" else "111111"
    results = ordered_overlap(monkeypatch, second,
                              lambda: verify(first, bad), lambda: verify(second, bad))
    assert sorted(results) == ["Invalid verification code", "Too many verification attempts"]
    with auth._connect() as db:
        assert db.execute(f"SELECT attempts FROM {table} WHERE {column}=?", (key,)).fetchone()[0] == 5
    with pytest.raises(ValueError, match="Too many"):
        verify(first, code)


@pytest.mark.parametrize("kind", ["login", "registration"])
def test_resend_cannot_report_success_after_consumption(setup, monkeypatch, kind):
    auth, first, second = setup
    if kind == "login":
        _, key, code = login_challenge(setup)
        verify = lambda: first.verify_login(key, code, IP)
        resend = lambda: second.resend_login_verification(key, IP)
        table = "login_verifications"
    else:
        key, code = first.start(EMAIL, PASSWORD)
        verify = lambda: first.verify(key, code)
        resend = lambda: second.resend(key)
        table = "pending_registrations"
    verified, resent = ordered_overlap(monkeypatch, second, verify, resend,
                                      second_at="generate")
    expected = "Login verification session expired" if kind == "login" else "No pending verification for this email"
    assert resent == expected
    if kind == "login":
        assert isinstance(verified, tuple)
        assert auth.get_user(verified[0]).email == EMAIL
    else:
        assert auth.get_user(verified).email == key
    with auth._connect() as db:
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_trusted_token_failure_rolls_back_consumption(setup):
    auth, first, second = setup
    user, challenge, code = login_challenge(setup)
    with auth._connect() as db:
        db.execute("CREATE TRIGGER fail_trust BEFORE INSERT ON trusted_login_devices BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="synthetic failure"):
        first.verify_login(challenge, code, IP)
    with auth._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM login_verifications").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM trusted_login_devices").fetchone()[0] == 0
        db.execute("DROP TRIGGER fail_trust")
    assert second.verify_login(challenge, code, IP)[0] == user.id


def test_registration_failure_rolls_back_consumption(setup):
    auth, first, second = setup
    email, code = first.start(EMAIL, PASSWORD)
    with auth._connect() as db:
        db.execute("CREATE TRIGGER fail_registration BEFORE INSERT ON users BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="synthetic failure"):
        first.verify(email, code)
    with auth._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM pending_registrations").fetchone()[0] == 1
        db.execute("DROP TRIGGER fail_registration")
    assert auth.get_user(second.verify(email, code)).email == email


def test_registration_start_cannot_recreate_consumed_pending_state(setup, monkeypatch):
    auth, first, second = setup
    email, code = first.start(EMAIL, PASSWORD)
    hashing, release = threading.Event(), threading.Event()
    real = registration._passwords.hash
    def hash_password(password):
        hashing.set()
        assert release.wait(10)
        return real(password)
    monkeypatch.setattr(registration, "_passwords", SimpleNamespace(hash=hash_password))
    with ThreadPoolExecutor(max_workers=1) as pool:
        started = pool.submit(second.start, email, PASSWORD)
        assert hashing.wait(10)
        first.verify(email, code)
        release.set()
        with pytest.raises(ValueError, match="already registered"):
            started.result(timeout=10)
    with auth._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM pending_registrations").fetchone()[0] == 0


@pytest.mark.parametrize("kind", ["login", "registration"])
def test_expiry_is_rechecked_after_waiting_for_writer(setup, monkeypatch, kind):
    auth, first, second = setup
    if kind == "login":
        _, key, code = login_challenge(setup)
        table, column = "login_verifications", "challenge_id"
        verify = lambda: second.verify_login(key, code, IP)
    else:
        key, code = first.start(EMAIL, PASSWORD)
        table, column = "pending_registrations", "email"
        verify = lambda: second.verify(key, code)
    now = [100.0]
    monkeypatch.setattr(registration.time, "time", lambda: now[0])
    with auth._connect() as db:
        db.execute(f"UPDATE {table} SET expires_at=101 WHERE {column}=?", (key,))
    connected = threading.Event()
    real = second._connect
    def connect():
        db = real()
        connected.set()
        return db
    monkeypatch.setattr(second, "_connect", connect)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with auth._connect() as writer:
            writer.execute("BEGIN IMMEDIATE")
            result = pool.submit(verify)
            assert connected.wait(10)
            now[0] = 102.0
        with pytest.raises(ValueError, match="expired"):
            result.result(timeout=10)


@pytest.mark.parametrize("kind", ["login", "registration"])
def test_resend_wins_before_old_code_verification(setup, monkeypatch, kind):
    auth, first, second = setup
    if kind == "login":
        user, key, old = login_challenge(setup)
        verify = lambda code: second.verify_login(key, code, IP)
        resend = lambda: first.resend_login_verification(key, IP)[2]
    else:
        key, old = first.start(EMAIL, PASSWORD)
        verify = lambda code: second.verify(key, code)
        resend = lambda: first.resend(key)[1]
    replacement = (int(old) + 1) % 1_000_000
    monkeypatch.setattr(registration.secrets, "randbelow", lambda _limit: replacement)
    new, stale = ordered_overlap(monkeypatch, second, resend, lambda: verify(old),
                                 first_at="generate")
    assert stale == "Invalid verification code"
    assert new == f"{replacement:06d}"
    verify(new)


def test_registration_pending_delete_failure_rolls_back_new_user(setup):
    auth, first, second = setup
    email, code = first.start(EMAIL, PASSWORD)
    with auth._connect() as db:
        db.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON pending_registrations BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="synthetic failure"):
        first.verify(email, code)
    with auth._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM pending_registrations").fetchone()[0] == 1
        db.execute("DROP TRIGGER fail_delete")
    assert auth.get_user(second.verify(email, code)).email == email


def test_http_login_verification_only_winner_receives_cookies(setup, monkeypatch):
    import asyncio
    import json
    from starlette.requests import Request
    from gpt_windows_connector import login_policy
    auth, first, second = setup
    user, challenge, code = login_challenge(setup)
    settings = SimpleNamespace(public_base_url="https://lucas.example.test", jwt_ttl_seconds=600)
    def verify(security):
        body = json.dumps({"challenge_id": challenge, "code": code}).encode()
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        request = Request({"type": "http", "method": "POST", "path": "/auth/login/verify", "headers": []}, receive)
        return asyncio.run(login_policy.verify(request, auth, security, settings, lambda _: IP))
    responses = ordered_overlap(monkeypatch, second,
                                lambda: verify(first), lambda: verify(second))
    assert sorted(r.status_code for r in responses) == [200, 400]
    winner = next(r for r in responses if r.status_code == 200)
    loser = next(r for r in responses if r.status_code == 400)
    cookies = winner.headers.getlist("set-cookie")
    assert any(c.startswith("gwc_access_token=") for c in cookies)
    assert any(c.startswith("gwc_trusted_login_device=") for c in cookies)
    assert loser.headers.getlist("set-cookie") == []


@pytest.mark.parametrize("kind", ["expired", "network"])
def test_rejected_login_resend_persists_invalidation(setup, kind):
    auth, first, second = setup
    _, challenge, code = login_challenge(setup)
    if kind == "expired":
        with auth._connect() as db:
            db.execute("UPDATE login_verifications SET expires_at=0")
    with pytest.raises(ValueError, match="expired|network changed"):
        first.resend_login_verification(challenge, IP if kind == "expired" else "192.0.2.11")
    with pytest.raises(ValueError, match="session expired"):
        second.verify_login(challenge, code, IP)


def test_registration_resend_preserves_expired_registration_renewal(setup):
    auth, first, second = setup
    email, code = first.start(EMAIL, PASSWORD)
    with auth._connect() as db:
        db.execute("UPDATE pending_registrations SET expires_at=0, attempts=5")
    email, code = first.resend(email)
    assert auth.get_user(second.verify(email, code)).email == email
