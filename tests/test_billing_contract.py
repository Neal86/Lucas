from pathlib import Path

from gpt_windows_connector.billing_ui import pricing_html


def test_pricing_contract():
    html=pricing_html()
    for text in ["$9.99","$19.99","$14.99","1,000 Requests","25,000 Requests","100,000 Requests","6 Nodes","Pro+ only"]:
        assert text in html


def test_expansion_is_pro_plus_only_in_backend():
    text=Path("src/gpt_windows_connector/billing.py").read_text(encoding="utf-8")
    assert "if not ent.can_buy_expansion" in text
    assert "Expansion Packs are available only on Pro+" in text


def test_billing_endpoints_and_webhook_exist():
    text=Path("src/gpt_windows_connector/webapp.py").read_text(encoding="utf-8")
    for route in ["/pricing","/billing","/api/billing/summary","/api/billing/checkout","/api/billing/expansion","/api/billing/portal","/api/billing/webhook"]:
        assert route in text


def test_dashboard_has_billing_entry_points():
    text=Path("src/gpt_windows_connector/web_assets.py").read_text(encoding="utf-8")
    assert "Plan & Billing" in text
    assert "Requests this period" in text
    assert "Manage Plan & Billing" in text


def test_billable_request_guard_is_before_node_rpc():
    text=Path("src/gpt_windows_connector/gateway.py").read_text(encoding="utf-8")
    start=text.index("async def _node_rpc")
    end=text.index("registry.rpc",start)
    prefix=text[start:end]
    assert "ensure_request_capacity" in prefix
    assert "ensure_node_active" in prefix
