from pathlib import Path

from gpt_windows_connector.billing_ui import dashboard_billing_html, pricing_html


def test_pricing_contract():
    html=pricing_html()
    for text in ["$9.99","$19.99","$14.99","1,000 Requests","25,000 Requests","100,000 Requests","6 Computers","Pro+ only"]:
        assert text in html


def test_expansion_is_pro_plus_only_in_backend():
    text=Path("src/gpt_windows_connector/billing.py").read_text(encoding="utf-8")
    assert "if not ent.can_buy_expansion" in text
    assert "Expansion Packs are available only on Pro+" in text


def test_billing_endpoints_and_webhook_exist():
    text=Path("src/gpt_windows_connector/webapp.py").read_text(encoding="utf-8")
    for route in ["/pricing","/billing","/api/billing/summary","/api/billing/checkout","/api/billing/expansion","/api/billing/portal","/api/billing/webhook"]:
        assert route in text
    server=Path("src/gpt_windows_connector/server.py").read_text(encoding="utf-8")
    assert '"/api/billing/webhook"' in server
    compose=Path("docker-compose.yml").read_text(encoding="utf-8")
    for key in ["STRIPE_SECRET_KEY","STRIPE_WEBHOOK_SECRET","STRIPE_PRICE_PRO","STRIPE_PRICE_PRO_PLUS","STRIPE_PRICE_EXPANSION"]:
        assert key in compose


def test_dashboard_has_billing_entry_points():
    from gpt_windows_connector.web_assets import DASHBOARD_HTML
    text=DASHBOARD_HTML
    assert 'data-view=\"billing\"' in text
    assert "Requests this period" in text
    assert "Manage Plan & Billing" in text
    fragment=dashboard_billing_html()
    assert 'id=\"billing\" class=\"view hidden\"' in fragment
    assert "Current plan" in fragment and "Expansion Pack" in fragment
    webapp=Path("src/gpt_windows_connector/webapp.py").read_text(encoding="utf-8")
    assert "dashboard_billing_html() + account_marker" in webapp
    assert "return HTMLResponse(_dashboard_html()" in webapp


def test_billable_request_guard_is_before_node_rpc():
    text=Path("src/gpt_windows_connector/gateway.py").read_text(encoding="utf-8")
    start=text.index("async def _node_rpc")
    end=text.index("registry.rpc",start)
    prefix=text[start:end]
    assert "ensure_request_capacity" in prefix
    assert "ensure_node_active" in prefix
