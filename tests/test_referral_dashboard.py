from gpt_windows_connector.referral_ui import dashboard_referral_html
from gpt_windows_connector.web_assets import DASHBOARD_HTML
from gpt_windows_connector.web_i18n_catalog import WEB_ZH_JS


def test_referral_nav_is_present_between_account_and_billing():
    account = DASHBOARD_HTML.index('data-view="account"')
    referral = DASHBOARD_HTML.index('data-view="referral"')
    billing = DASHBOARD_HTML.index('data-view="billing"')
    assert account < referral < billing
    assert 'Refer & Earn' in DASHBOARD_HTML


def test_dashboard_referral_contract():
    html = dashboard_referral_html()
    assert 'id="referral"' in html
    assert '300 OPs each' in html
    assert '3,000 OPs to you' in html
    assert 'No referral cap' in html
    assert 'No limit on total referrals or total referral rewards.' in html
    assert '/api/referrals/summary' in DASHBOARD_HTML
    assert "referral:'/refer'" in DASHBOARD_HTML


def test_referral_navigation_and_page_copy_are_localized():
    assert "'Refer & Earn':'邀请奖励'" in WEB_ZH_JS
    assert "'Help · Getting Started':'帮助 · 快速开始'" in WEB_ZH_JS
    assert "'Invite a friend':'邀请好友'" in WEB_ZH_JS
    assert "'Registered referrals':'已注册推荐'" in WEB_ZH_JS
    assert "'Paid referrals':'已付费推荐'" in WEB_ZH_JS
    assert "'No referral cap':'邀请人数无上限'" in WEB_ZH_JS
