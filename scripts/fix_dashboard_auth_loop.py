from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'src' / 'gpt_windows_connector' / 'web_core_runtime.py'
TEST = ROOT / 'tests' / 'test_dashboard_auth_boot.py'

s = CORE.read_text(encoding='utf-8')
old = "async function boot(){try{const me=await api(\\'/auth/me\\');state.user=me.user;showApp();userName.textContent=state.user.name||state.user.email;userEmail.textContent=state.user.email;accountName.textContent=state.user.name||\\'Account\\';accountEmail.textContent=state.user.email;accountProvider.textContent=state.user.provider;if([\\'admin\\',\\'super_admin\\'].includes(state.user.role))adminNav.classList.remove(\\'hidden\\');await refresh();routeFromLocation();startRealtime()}catch(e){showAuth()}}"
new = "async function boot(){let me;try{me=await api(\\'/auth/me\\')}catch(e){showAuth();return}state.user=me.user;showApp();userName.textContent=state.user.name||state.user.email;userEmail.textContent=state.user.email;accountName.textContent=state.user.name||\\'Account\\';accountEmail.textContent=state.user.email;accountProvider.textContent=state.user.provider;if([\\'admin\\',\\'super_admin\\'].includes(state.user.role))adminNav.classList.remove(\\'hidden\\');try{await refresh()}catch(e){console.error(\\'Dashboard refresh failed\\',e);toast(WEB_LANG===\\'zh\\'?\\'部分数据加载失败，请刷新重试\\':\\'Some dashboard data failed to load. Refresh to retry.\\')}routeFromLocation();startRealtime()}"
if old not in s:
    raise SystemExit('boot marker not found')
s = s.replace(old, new, 1)
CORE.write_text(s, encoding='utf-8')

TEST.write_text(r'''from pathlib import Path


def test_dashboard_boot_only_returns_to_login_when_auth_me_fails():
    text = (Path(__file__).resolve().parents[1] / 'src' / 'gpt_windows_connector' / 'web_core_runtime.py').read_text(encoding='utf-8')
    assert "try{me=await api(\\'/auth/me\\')}catch(e){showAuth();return}" in text
    assert "try{await refresh()}catch(e){console.error(\\'Dashboard refresh failed\\'" in text
    assert "Some dashboard data failed to load. Refresh to retry." in text
    assert "await refresh();routeFromLocation();startRealtime()}catch(e){showAuth()}" not in text
''', encoding='utf-8')
print('dashboard auth loop fix applied')
