from gpt_windows_connector import webapp


def test_public_home_has_search_metadata():
    html = webapp._landing_html()
    assert "Lucas MCP — Connect Any AI to Your Computer" in html
    assert 'rel="canonical" href="https://lucasmcp.com/"' in html
    assert 'property="og:title"' in html
    assert 'name="twitter:card"' in html
    assert 'application/ld+json' in html
    assert 'name="robots" content="index,follow' in html
    assert 'Lucas MCP computer connector' in html


def test_dashboard_is_noindex():
    html = webapp._dashboard_html()
    assert 'name="robots" content="noindex,nofollow,noarchive"' in html


def test_robots_and_sitemap_routes_are_registered():
    paths = {getattr(route, "path", None) for route in webapp.routes}
    assert "/robots.txt" in paths
    assert "/sitemap.xml" in paths
