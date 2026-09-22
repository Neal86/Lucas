from __future__ import annotations

from gpt_windows_connector.web_admin_runtime import ADMIN_SCRIPT
from gpt_windows_connector.web_assets import DASHBOARD_HTML
from gpt_windows_connector.web_dashboard_runtime_bundle import DASHBOARD_RUNTIME_SCRIPT


RUNTIME_SENTINEL = "const state={user:null,nodes:[],aiClients:[],billing:null};"


def test_dashboard_script_tags_are_balanced():
    assert DASHBOARD_HTML.count("<script") == DASHBOARD_HTML.count("</script>")


def test_dashboard_runtime_is_inside_script_element():
    index = DASHBOARD_HTML.index(RUNTIME_SENTINEL)
    last_open = DASHBOARD_HTML.rfind("<script", 0, index)
    last_close = DASHBOARD_HTML.rfind("</script>", 0, index)
    assert last_open > last_close
    assert "</script>" + RUNTIME_SENTINEL not in DASHBOARD_HTML


def test_dashboard_runtime_bundle_owns_html_boundary():
    assert DASHBOARD_RUNTIME_SCRIPT.startswith("<script>\n")
    assert DASHBOARD_RUNTIME_SCRIPT.endswith("</script>\n</body></html>")
    assert "</script>" not in ADMIN_SCRIPT
    assert "</body>" not in ADMIN_SCRIPT
    assert "</html>" not in ADMIN_SCRIPT


def test_dashboard_document_closes_once_after_runtime():
    assert DASHBOARD_HTML.rstrip().endswith("</body></html>")
    assert DASHBOARD_HTML.count("</body>") == 1
    assert DASHBOARD_HTML.count("</html>") == 1
