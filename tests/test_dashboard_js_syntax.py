import shutil
import subprocess
from html.parser import HTMLParser

from gpt_windows_connector import server


class _InlineScriptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_script = False
        self.in_inline_script = False
        self.current = []
        self.scripts = []
        self.outside_scripts = []
        self.unmatched_script_ends = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "script":
            return
        self.in_script = True
        self.in_inline_script = "src" not in dict(attrs)
        self.current = []

    def handle_data(self, data):
        if self.in_inline_script:
            self.current.append(data)
        elif not self.in_script:
            self.outside_scripts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "script":
            return
        if not self.in_script:
            self.unmatched_script_ends += 1
        if self.in_inline_script:
            code = "".join(self.current).strip()
            if code:
                self.scripts.append(code)
        self.in_script = self.in_inline_script = False
        self.current = []


def rendered_scripts():
    # server composes the production dashboard, including branding and login UI.
    # Checking the uncomposed template can miss broken final HTML boundaries.
    parser = _InlineScriptParser()
    parser.feed(server.webapp._dashboard_html())
    parser.close()
    return parser


def test_dashboard_inline_javascript_has_valid_syntax():
    """Check every actual inline script and their shared global declaration scope."""
    node = shutil.which("node")
    assert node, "Node.js is required; this smoke test must never be skipped"
    parser = rendered_scripts()
    assert parser.scripts, "Dashboard should contain inline JavaScript"
    scripts = parser.scripts + ["\n;\n".join(parser.scripts)]
    for index, script in enumerate(scripts):
        result = subprocess.run([node, "--check", "-"], input=script.encode("utf-8"),
                                capture_output=True, check=False)
        stderr = result.stderr.decode("utf-8", errors="replace")
        assert result.returncode == 0, f"Inline script #{index} is invalid:\n{stderr}"


def test_complete_dashboard_runtime_is_inside_one_script():
    parser = rendered_scripts()
    runtime = [script for script in parser.scripts if "const state=" in script]
    assert len(runtime) == 1, "The dashboard runtime must be executable script, not body text"
    for required in (
        "function loadBillingView(", "function loadReferralView(", "function api(",
        "function showRegister(", "function login(", "function resetLoginVerification(",
        "function boot(", "function startRealtime(", "function adminTab(",
        "window.maybeStartOnboarding = maybeStartOnboarding;", "boot();",
    ):
        assert runtime[0].count(required) == 1, required


def test_dashboard_does_not_render_javascript_as_body_text():
    parser = rendered_scripts()
    assert parser.unmatched_script_ends == 0
    assert not parser.in_script
    outside = "".join(parser.outside_scripts)
    for leaked in ("const state=", "async function api(", "function showRegister(",
                   "async function login(", "async function boot(", "function adminTab("):
        assert leaked not in outside, f"Dashboard JavaScript leaked outside script: {leaked}"


def test_dashboard_html_is_not_blank_shell():
    html = server.webapp._dashboard_html()
    assert "<body" in html.lower()
    for required in ('id="app"', 'id="auth"', 'id="taskRunTable"', "loadTaskRuns"):
        assert required in html
