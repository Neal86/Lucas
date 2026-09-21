from __future__ import annotations

from pathlib import Path

from gpt_windows_connector.web_cache_policy import HTML_NO_CACHE_HEADERS, html_no_cache_headers
from gpt_windows_connector import webapp


def test_html_cache_policy_disables_stale_page_reuse():
    headers = html_no_cache_headers()
    assert headers["Cache-Control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert headers["Pragma"] == "no-cache"
    assert headers["Expires"] == "0"


def test_public_home_uses_no_cache_policy():
    source = Path(webapp.__file__).read_text(encoding="utf-8")
    assert "return HTMLResponse(html, headers=html_no_cache_headers())" in source


def test_extra_headers_can_be_merged():
    headers = html_no_cache_headers({"X-Test": "ok"})
    assert headers["X-Test"] == "ok"
    assert headers["Cache-Control"].startswith("no-store")
