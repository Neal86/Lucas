from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector.oauth import OAuthProvider
from gpt_windows_connector.security import LocalSecurityPolicy
from gpt_windows_connector.access_control import preset_security
from gpt_windows_connector.billing_ui import pricing_html
from gpt_windows_connector.settings_constants import PRESETS
from gpt_windows_connector.settings_helpers import detect_security_preset


def test_oauth_client_identity_survives_verified_access_token(tmp_path):
    auth=AuthStore(tmp_path/'auth.db','source-audit-secret-'*4)
    user=auth.register('audit@example.com','valid-password-123')
    provider=OAuthProvider(tmp_path/'auth.db',auth,'http://localhost')
    token=provider.tokens(user,'client-exact','lucas',False)['access_token']
    assert auth.verify_token(token).client_id=='client-exact'
    assert auth.verify_token(auth.issue_token(user)).client_id is None


def test_local_approval_outcomes_are_recorded(monkeypatch):
    policy=LocalSecurityPolicy({'security':preset_security('full_access')})
    policy.authorize('browser.inspect',{})
    assert policy.audit_decisions[-1]['decision']=='allowed_by_policy'
    monkeypatch.setattr(policy,'_prompt',lambda *args: True)
    policy.authorize('computer.click',{})
    assert policy.audit_decisions[-1]['decision']=='approved_locally'


def test_pricing_register_and_localization():
    html=pricing_html()
    assert 'href="/dashboard?signup=1">Start Free Beta' in html
    assert 'navigator.language' in html and '测试期间免费' in html
    assert 'position:sticky;top:0' in html


def test_auto_and_full_access_presets_remain_distinct():
    for name in ('帮我批准','完全访问权限'):
        p=PRESETS[name]
        assert detect_security_preset(p['approval_policy'],p['network_external'],p['network_lan'],p['block_silent_network'])==name


def test_beta_blocks_all_paid_entry_points_before_stripe(monkeypatch):
    import pytest
    from gpt_windows_connector.billing import BillingService
    service=object.__new__(BillingService)
    monkeypatch.setenv("LUCAS_BETA_FREE", "1")
    with pytest.raises(RuntimeError,match="disabled"):
        service.checkout(None,"pro")
    with pytest.raises(RuntimeError,match="disabled"):
        service.add_expansion("user")
    with pytest.raises(PermissionError,match="disabled"):
        service.portal("user")
