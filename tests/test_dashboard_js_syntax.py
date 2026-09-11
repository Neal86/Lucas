import shutil
import subprocess
from html.parser import HTMLParser

from gpt_windows_connector.web_assets import DASHBOARD_HTML


class _InlineScriptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_inline_script = False
        self.current = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "script":
            return
        attrs = dict(attrs)
        self.in_inline_script = "src" not in attrs
        self.current = []

    def handle_data(self, data):
        if self.in_inline_script:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.in_inline_script:
            code = "".join(self.current).strip()
            if code:
                self.scripts.append(code)
            self.in_inline_script = False
            self.current = []


def test_dashboard_inline_javascript_has_valid_syntax():
    """Fail hard on any inline JavaScript syntax error that can blank the UI."""
    node = shutil.which("node")
    assert node, "Node.js is required; this smoke test must never be skipped"

    parser = _InlineScriptParser()
    parser.feed(DASHBOARD_HTML)
    assert parser.scripts, "Dashboard should contain inline JavaScript"

    for index, script in enumerate(parser.scripts):
        result = subprocess.run(
            [node, "--check", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, f"Inline script #{index} is invalid:\n{result.stderr}"


def test_dashboard_html_is_not_blank_shell():
    assert "<body" in DASHBOARD_HTML.lower()
    assert 'id="app"' in DASHBOARD_HTML
    assert 'id="auth"' in DASHBOARD_HTML
    assert 'id="taskRunTable"' in DASHBOARD_HTML
    assert "loadTaskRuns" in DASHBOARD_HTML
