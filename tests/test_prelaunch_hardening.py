from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector.billing import BillingService


def test_first_public_user_is_not_auto_admin(tmp_path, monkeypatch):
    monkeypatch.delenv("GWC_SUPER_ADMIN_EMAIL", raising=False)
    store = AuthStore(tmp_path / "gateway.db", "x" * 40)
    user = store.register("normal@example.com", "a-long-enough-password")
    assert user.role == "user"


def test_configured_owner_becomes_super_admin(tmp_path, monkeypatch):
    monkeypatch.setenv("GWC_SUPER_ADMIN_EMAIL", "owner@example.com")
    store = AuthStore(tmp_path / "gateway.db", "x" * 40)
    user = store.register("owner@example.com", "a-long-enough-password")
    assert user.role == "super_admin"


def test_billing_summary_is_safe_without_stripe(tmp_path, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    store = AuthStore(tmp_path / "gateway.db", "x" * 40)
    user = store.register("billing@example.com", "a-long-enough-password")
    svc = BillingService(tmp_path / "gateway.db", "https://lucasmcp.com")
    out = svc.summary(user.id)
    assert out["billing_interval"] == "month"
