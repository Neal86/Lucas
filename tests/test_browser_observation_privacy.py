"""Execute the production CDP observer against a synthetic DOM, without a browser."""
import asyncio
import json
import shutil
import subprocess

import pytest

from gpt_windows_connector import browser, browser_semantic
from gpt_windows_connector.access_control import preset_security
from gpt_windows_connector.executor import Executor


NODE = shutil.which("node")
RUNTIME = pytest.mark.skipif(NODE is None, reason="Node.js is required for observation runtime tests")
PASSWORD = "SYNTHETIC-PASSWORD-DO-NOT-USE"


class RuntimePage:
    url = "https://fixture.invalid/login"

    def __init__(self, elements):
        self.elements = elements
        self.evaluations = 0

    async def title(self):
        return "Synthetic login fixture"

    def locator(self, selector):
        assert selector == "button,a,input,textarea,select,[role=button],[role=link],[contenteditable=true]"
        return self

    async def evaluate_all(self, expression, limit):
        self.evaluations += 1
        # Execute the exact JS supplied by browser_semantic.observe, rather than
        # duplicating its redaction or evaluating only a source-text assertion.
        script = """
        const elements = JSON.parse(process.argv[1]).map(item => ({
          tagName: 'INPUT', innerText: '', value: '', id: '', disabled: false,
          offsetWidth: 100, offsetHeight: 20, ...item,
          type: (item.attrs?.type || 'text').toLowerCase(),
          getAttribute(name) { return this.attrs?.[name] ?? null; },
          getClientRects() { return this.offsetWidth || this.offsetHeight ? [{}] : []; }
        }));
        console.log(JSON.stringify((""" + expression + ")(elements, " + json.dumps(limit) + ")));"
        result = subprocess.run(
            [NODE, "-e", script, json.dumps(self.elements)],
            capture_output=True, text=True, check=True, timeout=10,
        )
        return json.loads(result.stdout)


@pytest.fixture
def session(monkeypatch):
    def register(pages, owner_id="owner"):
        class Context:
            pass

        context = Context()
        context.pages = pages
        sid = "synthetic-observation-session"
        monkeypatch.setitem(browser._SESSIONS, sid, browser.BrowserSession(context=context, owner_id=owner_id))
        return sid

    return register


@RUNTIME
@pytest.mark.parametrize("password_type", ["password", "PASSWORD", "PaSsWoRd"])
@pytest.mark.parametrize("inner_text", ["", "SYNTHETIC-PASSWORD-INNER-TEXT"])
def test_executor_observe_redacts_password_without_removing_metadata(tmp_path, session, password_type, inner_text):
    page = RuntimePage([{
        "id": "password", "value": PASSWORD, "innerText": inner_text,
        "attrs": {"type": password_type, "name": "login-password", "role": "textbox",
                  "aria-label": "Password", "placeholder": "Enter password"},
    }, {"id": "name", "value": "  Synthetic user  "}])
    sid = session([page])
    executor = Executor((tmp_path,), {"security": preset_security("full_access")}, owner_id="owner")

    observed = asyncio.run(executor.call("browser.observe", {"session_id": sid, "workspace": str(tmp_path)}))

    assert observed["url"] == page.url
    assert observed["title"] == "Synthetic login fixture"
    assert observed["elements"][0] == {
        "index": 0, "tag": "input", "role": "textbox", "text": "", "name": "login-password",
        "aria_label": "Password", "placeholder": "Enter password", "type": password_type,
        "id": "password", "disabled": False, "visible": True,
    }
    assert observed["elements"][1]["text"] == "Synthetic user"
    assert PASSWORD not in json.dumps(observed)
    if inner_text:
        assert inner_text not in json.dumps(observed)
    assert page.evaluations == 1


@RUNTIME
def test_observe_preserves_non_password_text_metadata_visibility_and_limits(session):
    unused = RuntimePage([{"value": "Wrong page"}])
    page = RuntimePage([
        {"id": "ordinary", "value": "  ordinary value  ", "disabled": True, "attrs": {"name": "ordinary"}},
        {"id": "hidden", "value": "Hidden", "offsetWidth": 0, "offsetHeight": 0},
        {"id": "password", "value": "", "attrs": {"type": "password"}},
        {"id": "submit", "tagName": "BUTTON", "innerText": "  Submit  ", "value": "Unused button value"},
        {"id": "notes", "tagName": "TEXTAREA", "value": "x" * 301},
    ])
    sid = session([unused, page])

    observed = asyncio.run(browser_semantic.observe(sid, page_index=1))
    assert [item["id"] for item in observed["elements"]] == ["ordinary", "password", "submit", "notes"]
    assert [item["text"] for item in observed["elements"]] == ["ordinary value", "", "Submit", "x" * 300]
    assert observed["elements"][0]["disabled"] is True
    assert observed["elements"][0]["name"] == "ordinary"
    limited = asyncio.run(browser_semantic.observe(sid, page_index=1, limit=2))
    assert [item["id"] for item in limited["elements"]] == ["ordinary"]
    assert unused.evaluations == 0


@pytest.mark.parametrize("session_owner", ["another-owner", None])
def test_executor_rejects_unowned_observation_before_evaluating_page(tmp_path, session, session_owner):
    page = RuntimePage([{"id": "password", "value": PASSWORD, "attrs": {"type": "password"}}])
    sid = session([page], owner_id=session_owner)
    executor = Executor((tmp_path,), {"security": preset_security("full_access")}, owner_id="owner")

    with pytest.raises(PermissionError, match="another Lucas account"):
        asyncio.run(executor.call("browser.observe", {"session_id": sid}))
    assert page.evaluations == 0
