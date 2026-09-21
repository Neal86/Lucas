from __future__ import annotations

from pathlib import Path

from gpt_windows_connector import webapp
from gpt_windows_connector.web_landing import LANDING_HTML
from gpt_windows_connector.web_smoke_routes import WEB_SMOKE_ROUTES


def test_dashboard_shell_removes_landing_by_component_not_formatting():
    source = Path(webapp.__file__).read_text(encoding="utf-8")
    assert 'html = html.replace(LANDING_HTML, "", 1)' in source
    assert "section_end = html.index" not in source
    assert "css_start = html.index" not in source


def test_dashboard_html_renders_without_landing():
    html = webapp._dashboard_html()
    assert LANDING_HTML not in html
    assert 'id="auth"' in html
    assert 'id="app"' in html or 'id="dashboard"' in html


def test_release_smoke_covers_all_primary_dashboard_routes():
    route_map = dict(WEB_SMOKE_ROUTES)
    for path in ("/", "/dashboard", "/nodes", "/ai-connections", "/task-runs", "/logs", "/account", "/pricing", "/docs/computer-node"):
        assert path in route_map
        assert route_map[path] == 200
