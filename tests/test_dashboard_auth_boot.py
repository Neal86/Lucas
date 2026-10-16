from gpt_windows_connector.web_core_runtime import CORE_SCRIPT
from gpt_windows_connector.web_session_lifecycle_runtime import SESSION_BOOT_SCRIPT


def test_dashboard_boot_only_returns_to_login_when_auth_me_fails():
    # Inspect the actual composed owner, not its former source-file location.
    assert CORE_SCRIPT.count(SESSION_BOOT_SCRIPT) == 1
    assert "try{me=await api('/auth/me',{},owns)}catch(e){if(owns())showAuth();return}" in SESSION_BOOT_SCRIPT
    assert "try{await refresh(owns)}catch(e){" in SESSION_BOOT_SCRIPT
    assert "if(!owns())return;\n    console.error('Dashboard refresh failed',e);" in SESSION_BOOT_SCRIPT
    assert "Some dashboard data failed to load. Refresh to retry." in SESSION_BOOT_SCRIPT
    assert "await refresh();routeFromLocation();startRealtime()}catch(e){showAuth()}" not in CORE_SCRIPT
