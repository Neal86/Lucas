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
            errors = []
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(base + "/dashboard")
                result = page.evaluate("""async()=>{const r=await fetch('/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'e2e-admin@example.com',password:'A-very-long-test-password-123',name:'E2E Admin'})});return [r.status,await r.text()]}""")
                assert result[0] in (200, 201), result
                for path in ["/dashboard", "/nodes", "/ai-connections", "/refer", "/billing", "/admin", "/privacy", "/terms", "/refunds", "/contact"]:
                    page.goto(base + path, wait_until="networkidle")
                    assert "async function api(" not in page.locator("body").inner_text()
                assert not errors, errors
                browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=10)
