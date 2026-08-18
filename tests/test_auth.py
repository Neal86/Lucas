from pathlib import Path

import pytest

from gpt_windows_connector.auth import AuthStore


def test_email_registration_login_and_token(tmp_path: Path):
    store = AuthStore(tmp_path / "gateway.db", "test-secret", 3600)
    user = store.register("User@example.com", "very-secure-password", "User")
    assert user.email == "user@example.com"
    logged_in = store.login("user@example.com", "very-secure-password")
    assert logged_in.id == user.id
    token = store.issue_token(user)
    assert store.verify_token(token).id == user.id


def test_email_password_rejected(tmp_path: Path):
    store = AuthStore(tmp_path / "gateway.db", "test-secret", 3600)
    with pytest.raises(ValueError):
        store.register("user@example.com", "short")


def test_google_account_can_link_existing_email(tmp_path: Path):
    store = AuthStore(tmp_path / "gateway.db", "test-secret", 3600)
    first = store.register("user@example.com", "very-secure-password")
    google = store.google_login(sub="google-sub-1", email="user@example.com", name="Google User", picture=None)
    assert google.id == first.id
    assert google.provider == "google"
