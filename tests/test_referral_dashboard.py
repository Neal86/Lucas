from gpt_windows_connector.referral_ui import dashboard_referral_html
from gpt_windows_connector.web_assets import DASHBOARD_HTML


def test_referral_nav_is_present_between_account_and_billing():
    account = DASHBOARD_HTML.index('data-view="account"')
    referral = DASHBOARD_HTML.index('data-view="referral"')
    billing = DASHBOARD_HTML.index('data-view="billing"')
    assert account < referral < billing
    assert 'Refer & Earn' in DASHBOARD_HTML


def test_dashboard_referral_contract():
    html = dashboard_referral_html()
    assert 'id="referral"' in html
    assert '1,000 bonus Requests' in html
    assert '10,000 bonus Requests' in html
    assert '/api/referrals/summary' in DASHBOARD_HTML
    assert "referral:'/refer'" in DASHBOARD_HTML
