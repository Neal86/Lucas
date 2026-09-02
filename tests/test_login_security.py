from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector.registration_security import RegistrationSecurity


def test_login_verification_trusts_same_device_and_ip(tmp_path):
    db_path = tmp_path / "gateway.db"
    auth = AuthStore(db_path, "test-secret")
    security = RegistrationSecurity(db_path)
    user = auth.register("login@example.com", "very-secure-password")

    challenge_id, code = security.start_login_verification(
        user.id, user.email, "203.0.113.10", True
    )
    user_id, remember, token = security.verify_login(
        challenge_id, code, "203.0.113.10"
    )

    assert user_id == user.id
    assert remember is True
    assert token
    assert security.is_trusted_login(user.id, token, "203.0.113.10") is True


def test_login_ip_change_invalidates_trusted_device(tmp_path):
    db_path = tmp_path / "gateway.db"
    auth = AuthStore(db_path, "test-secret")
    security = RegistrationSecurity(db_path)
    user = auth.register("ipchange@example.com", "very-secure-password")

    challenge_id, code = security.start_login_verification(
        user.id, user.email, "203.0.113.10", True
    )
    _, _, token = security.verify_login(challenge_id, code, "203.0.113.10")

    assert security.is_trusted_login(user.id, token, "198.51.100.22") is False
    assert security.is_trusted_login(user.id, token, "203.0.113.10") is False


def test_login_verification_rejects_network_change(tmp_path):
    db_path = tmp_path / "gateway.db"
    auth = AuthStore(db_path, "test-secret")
    security = RegistrationSecurity(db_path)
    user = auth.register("challenge@example.com", "very-secure-password")

    challenge_id, code = security.start_login_verification(
        user.id, user.email, "203.0.113.10", False
    )

    try:
        security.verify_login(challenge_id, code, "198.51.100.22")
        assert False, "network change must invalidate the challenge"
    except ValueError as exc:
        assert "network changed" in str(exc).lower()


def test_login_verification_without_remember_does_not_create_device_token(tmp_path):
    db_path = tmp_path / "gateway.db"
    auth = AuthStore(db_path, "test-secret")
    security = RegistrationSecurity(db_path)
    user = auth.register("noremember@example.com", "very-secure-password")

    challenge_id, code = security.start_login_verification(
        user.id, user.email, "203.0.113.10", False
    )
    _, remember, token = security.verify_login(challenge_id, code, "203.0.113.10")

    assert remember is False
    assert token is None
