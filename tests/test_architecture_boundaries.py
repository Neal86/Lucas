from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "gpt_windows_connector"


def test_large_payloads_are_not_embedded_in_orchestrators():
    webapp=(PKG/"webapp.py").read_text(encoding="utf-8"); gateway=(PKG/"gateway.py").read_text(encoding="utf-8"); node=(PKG/"node.py").read_text(encoding="utf-8"); settings=(PKG/"settings_ui.py").read_text(encoding="utf-8")
    assert "DASHBOARD_HTML =" not in webapp and "class NodeAuthStore" not in gateway and "class UserNodeBindingStore" not in gateway and "class BrowserEventHub" not in gateway
    assert "def _prompt_access_request" not in node and "SETTINGS_EN =" not in settings


def test_isolation_modules_exist():
    required={"web_assets.py","gateway_stores.py","gateway_events.py","node_approval.py","settings_constants.py","settings_helpers.py","web_landing.py","web_billing_runtime.py","web_core_runtime.py","web_admin_runtime.py","plugin_sync.py","plugin_host.py","plugin_tools.py","local_account.py","settings_account_ui.py"}
    assert required <= {p.name for p in PKG.iterdir() if p.is_file()}


def test_orchestrator_size_budgets_do_not_regress():
    budgets={"web_assets.py":5000,"webapp.py":45000,"gateway.py":51000,"node.py":30000,"settings_ui.py":57500,"tray.py":23000}
    failures=[]
    for name,budget in budgets.items():
        size=(PKG/name).stat().st_size
        if size>budget: failures.append(f"{name}: {size} > {budget}")
    assert not failures,"Architecture size budget exceeded: "+"; ".join(failures)
