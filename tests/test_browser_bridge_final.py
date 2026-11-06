from pathlib import Path
import subprocess
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]


def test_popup_has_exactly_three_readonly_fields():
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.fields = []
            self.controls = []
        def handle_starttag(self, tag, attrs):
            if tag == "dd": self.fields.append(dict(attrs)["id"])
            if tag in {"button", "input", "select", "a", "form"}: self.controls.append(tag)
    parser = Parser()
    parser.feed((ROOT / "src/gpt_windows_connector/browser_bridge_extension/popup.html").read_text())
    assert parser.fields == ["status", "profile", "tabState"]
    assert parser.controls == []


def test_shipped_worker_and_popup_runtime_with_api_doubles():
    result = subprocess.run(["node", "tests/js/browser_bridge_runtime.cjs"], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
