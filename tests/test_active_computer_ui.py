from gpt_windows_connector.webapp import _dashboard_html


def test_computers_offer_activation_for_over_limit_bindings():
    html=_dashboard_html()
    assert "/api/nodes/" in html
    assert "/activate" in html
    assert "Computer activated" in html
    assert "Activate</button>" in html
