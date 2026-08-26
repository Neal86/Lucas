from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector.registration_security import RegistrationSecurity


def test_pending_registration_only_creates_user_after_verification(tmp_path):
    db_path = tmp_path / "gateway.db"
    auth = AuthStore(db_path, "test-secret")
    security = RegistrationSecurity(db_path)
    email, code = security.start("BotTest@example.com", "very-secure-password", "Bot Test")

    with auth._connect() as db:
        assert db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone() is None

    user_id = security.verify(email, code)
    user = auth.get_user(user_id)
    assert user.email == "bottest@example.com"
    assert user.status == "active"


def test_verification_code_is_single_use_and_attempt_limited(tmp_path):
    db_path = tmp_path / "gateway.db"
    AuthStore(db_path, "test-secret")
    security = RegistrationSecurity(db_path)
    email, code = security.start("test@example.com", "very-secure-password")

    for _ in range(5):
        try:
            security.verify(email, "000000" if code != "000000" else "111111")
        except ValueError:
            pass
    try:
        security.verify(email, code)
        assert False, "verification should be locked after five bad attempts"
    except ValueError as exc:
        assert "Too many" in str(exc)


def test_registration_rate_limiter():
    security = object.__new__(RegistrationSecurity)
    security._buckets = {}
    assert security.allow("ip:1", 2, 60)
    assert security.allow("ip:1", 2, 60)
    assert not security.allow("ip:1", 2, 60)
