from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "src" / "gpt_windows_connector"
BG = (BASE / "browser_bridge_extension" / "background.js").read_text(encoding="utf-8")
CONTENT = (BASE / "browser_bridge_extension" / "content.js").read_text(encoding="utf-8")
ROUTER = (BASE / "browser_router.py").read_text(encoding="utf-8")


def test_bridge_requires_owned_tab_instead_of_active_human_tab():
    assert "owns(Number(tabId),taskKey)" in BG
    assert "No active AI tab for this task" in BG
    assert 'usable.find(t=>t.active)' not in BG


def test_bridge_creates_background_tabs_and_binds_task():
    assert 'active:false' in BG
    assert "await registerTab(t.id,taskKey)" in BG
    assert 'bridge_params["task_key"] = task_key' in ROUTER


def test_human_takeover_pauses_ai_and_does_not_close_tab():
    assert 'lucas_human_takeover' in BG
    assert 'setPaused(sender.tab.id,true)' in BG
    assert 'if (state.paused) throw new Error' in BG
    assert 'lucas-ai-tab-indicator' in CONTENT
    assert '接管 / Take over' in CONTENT


def test_claim_and_resume_require_confirmation():
    assert 'operation == "claim_tab"' in ROUTER
    assert 'operation_params.get("user_confirmed") is not True' in ROUTER
    assert 'p.user_confirmed!==true' in BG
