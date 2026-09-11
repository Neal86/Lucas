import os
import socket
import subprocess
import sys
import tempfile
import time

import pytest

pytestmark = pytest.mark.skipif(os.getenv("RUN_BROWSER_E2E") != "1", reason="browser e2e only")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_dashboard_browser_smoke():
    from playwright.sync_api import sync_playwright
    import urllib.request

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory() as td:
        env = os.environ.copy()
        env.update({
            "GWC_DATA_DIR": td,
            "GWC_PUBLIC_BASE_URL": base,
            "GWC_SUPER_ADMIN_EMAIL": "e2e-admin@example.com",
            "GWC_PORT": str(port),
            "GWC_HOST": "127.0.0.1",
        })
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "gpt_windows_connector.webapp:app", "--host", "127.0.0.1", "--port", str(port)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.time() + 20
            while time.time() < deadline:
                try:
                    urllib.request.urlopen(base + "/", timeout=1)
                    break
                except Exception:
                    time.sleep(0.2)
            else:
                raise AssertionError("Local Lucas server did not become ready")

            errors = []
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(base + "/dashboard", wait_until="domcontentloaded")

                result = page.evaluate("""async()=>{const r=await fetch('/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'e2e-admin@example.com',password:'A-very-long-test-password-123',name:'E2E Admin'})});return [r.status,await r.text()]}""")
                assert result[0] in (200, 201), result

                me = page.evaluate("""async()=>{const r=await fetch('/auth/me');return [r.status,await r.json()]}""")
                assert me[0] == 200, me
                assert me[1]["user"]["email"] == "e2e-admin@example.com"
                assert me[1]["user"]["role"] == "super_admin"

                protected_paths = [
                    "/dashboard", "/nodes", "/ai-connections", "/task-runs", "/logs",
                    "/account", "/refer", "/billing", "/admin", "/admin/users",
                    "/admin/usage", "/admin/nodes", "/admin/operations",
                    "/admin/subscriptions", "/admin/system",
                ]
                public_paths = ["/pricing", "/privacy", "/terms", "/refunds", "/contact"]
                for path in protected_paths + public_paths:
                    response = page.goto(base + path, wait_until="networkidle")
                    assert response is not None and response.status < 400, (path, response.status if response else None)
                    assert "async function api(" not in page.locator("body").inner_text()

                api_contracts = page.evaluate("""async()=>{
                    async function get(path){const r=await fetch(path);let body={};try{body=await r.json()}catch{}return {status:r.status,body}}
                    return {
                      nodes:await get('/api/nodes'),
                      tasks:await get('/api/task-runs?limit=10&days=30'),
                      logs:await get('/api/logs?limit=10'),
                      ai:await get('/api/ai-connections'),
                      billing:await get('/api/billing/summary'),
                      adminDashboard:await get('/api/admin/dashboard'),
                      adminUsers:await get('/api/admin/users'),
                      adminUsage:await get('/api/admin/usage'),
                      adminNodes:await get('/api/admin/nodes'),
                      adminOperations:await get('/api/admin/operations?action=smoke'),
                      adminSubscriptions:await get('/api/admin/subscriptions'),
                      adminSystem:await get('/api/admin/system')
                    }
                }""")

                for name, result in api_contracts.items():
                    assert result["status"] == 200, (name, result)
                assert isinstance(api_contracts["nodes"]["body"].get("nodes"), list)
                assert isinstance(api_contracts["nodes"]["body"].get("billing"), dict)
                assert isinstance(api_contracts["tasks"]["body"].get("runs"), list)
                assert {"task_runs", "operations", "duration_ms"} <= set(api_contracts["tasks"]["body"].get("summary", {}))
                assert isinstance(api_contracts["logs"]["body"].get("logs"), list)
                assert isinstance(api_contracts["ai"]["body"].get("clients"), list)
                assert {"plan", "request_limit", "requests_used", "node_limit", "ai_account_limit"} <= set(api_contracts["billing"]["body"])
                assert {"users", "operations_today", "operations_30d", "online_nodes"} <= set(api_contracts["adminDashboard"]["body"])
                assert isinstance(api_contracts["adminUsers"]["body"].get("users"), list)
                assert {"operations_30d", "success_rate", "daily"} <= set(api_contracts["adminUsage"]["body"])
                assert isinstance(api_contracts["adminNodes"]["body"].get("nodes"), list)
                assert isinstance(api_contracts["adminOperations"]["body"].get("operations"), list)
                assert isinstance(api_contracts["adminSubscriptions"]["body"].get("subscriptions"), list)
                assert api_contracts["adminSystem"]["body"].get("gateway") == "healthy"
                assert api_contracts["adminSystem"]["body"].get("database") == "healthy"

                logout = page.evaluate("""async()=>{const r=await fetch('/api/logout',{method:'POST'});return [r.status,await r.json()]}""")
                assert logout[0] == 200 and logout[1].get("ok") is True
                after_logout = page.evaluate("""async()=>{const r=await fetch('/auth/me');return r.status}""")
                assert after_logout == 401

                assert not errors, errors
                browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=10)
