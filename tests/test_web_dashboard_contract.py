from __future__ import annotations

from pathlib import Path
from html.parser import HTMLParser

from gpt_windows_connector import server, webapp
from gpt_windows_connector.web_landing import LANDING_HTML
from gpt_windows_connector.web_smoke_routes import WEB_SMOKE_ROUTES


class _Structure(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = set()
        self.classes = set()
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        self.classes.update((attrs.get("class") or "").split())


def test_dashboard_shell_removes_landing_by_component_not_formatting():
    source = Path(webapp.__file__).read_text(encoding="utf-8")
    assert 'html = html.replace(LANDING_HTML, "", 1)' in source
    assert "section_end = html.index" not in source
    assert "css_start = html.index" not in source


def test_dashboard_html_renders_without_landing():
    # Exercise the final server composition after logo/auth replacements.
    html = server.webapp._dashboard_html()
    structure = _Structure(html)
    assert "landing" not in structure.ids
    assert not {"landing-nav", "landing-footer", "hero", "final-cta"} & structure.classes
    assert LANDING_HTML not in html
    assert 'id="auth"' in html
    assert 'id="app"' in html or 'id="dashboard"' in html


def test_release_smoke_covers_all_primary_dashboard_routes():
    route_map = dict(WEB_SMOKE_ROUTES)
    for path in ("/", "/dashboard", "/nodes", "/ai-connections", "/task-runs", "/logs", "/account", "/pricing", "/docs/computer-node"):
        assert path in route_map
        assert route_map[path] == 200


def test_public_landing_keeps_its_component_after_dashboard_composition():
    html = webapp._landing_html()
    structure = _Structure(html)
    assert "landing" in structure.ids
    assert {"landing-nav", "landing-footer", "hero", "final-cta"} <= structure.classes
    expected = LANDING_HTML.replace('onclick="openAuth()"', 'onclick="location.href=\'/dashboard\'"')
    assert expected in html
    assert "With $0 Token Fees" in html
    assert "const state=" not in html
