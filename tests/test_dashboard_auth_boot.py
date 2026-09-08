from pathlib import Path


def test_dashboard_boot_only_returns_to_login_when_auth_me_fails():
    text = (Path(__file__).resolve().parents[1] / 'src' / 'gpt_windows_connector' / 'web_core_runtime.py').read_text(encoding='utf-8')
    assert "try{me=await api(\\'/auth/me\\')}catch(e){showAuth();return}" in text
    assert "try{await refresh()}catch(e){console.error(\\'Dashboard refresh failed\\'" in text
    assert "Some dashboard data failed to load. Refresh to retry." in text
    assert "await refresh();routeFromLocation();startRealtime()}catch(e){showAuth()}" not in text
