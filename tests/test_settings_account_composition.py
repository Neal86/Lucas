"""Source-only Settings composition contracts with no GUI, network or credentials."""
from pathlib import Path
from types import SimpleNamespace

from gpt_windows_connector import settings_account_integration as integration
from gpt_windows_connector import settings_helpers
from gpt_windows_connector.settings_navigation import NAV_EN, PAGE_ORDER, PAGE_DESCRIPTIONS, PAGE_DESCRIPTIONS_EN
from gpt_windows_connector.update_ui import InAppUpdater


OLD_ORDER = ('常规', '安全', '用户与权限', '文件访问', '网络', '任务记录', '日志', '系统访问')


def test_existing_navigation_preserved_and_account_localized():
    assert tuple(name for name in PAGE_ORDER if name != '账号') == OLD_ORDER
    assert PAGE_ORDER[1] == '账号'
    assert set(NAV_EN) == set(PAGE_DESCRIPTIONS) == set(PAGE_ORDER)
    assert NAV_EN['账号'] == 'Account'
    assert 'separate local approval' in PAGE_DESCRIPTIONS_EN['账号']


def test_account_page_constructs_only_origin_bound_client_and_scroll_wrapper(tmp_path, monkeypatch):
    monkeypatch.setattr(integration, 'CONFIG_DIR', tmp_path)
    calls = []
    wrapper = object()
    def page(**kwargs):
        calls.append(kwargs)
        assert kwargs['client'].base_url == 'https://lucas.example'
        assert kwargs['client'].state_path == tmp_path / 'account-session.json'
        assert kwargs['scroll_page']() == ('wrap', 'body')
        return wrapper
    monkeypatch.setattr(integration, 'build_account_page', page)
    pages = {}
    integration.install_account_page(pages, object(), object(), {}, 'Arial', 'wss://lucas.example/ws/node', lambda zh, en: en, lambda: ('wrap', 'body'))
    assert pages == {'账号': wrapper}
    assert not list(tmp_path.iterdir())
    assert len(calls) == 1


def test_invalid_gateway_keeps_settings_open_for_correction(tmp_path, monkeypatch):
    monkeypatch.setattr(integration, 'CONFIG_DIR', tmp_path)
    labels = []
    class Label:
        def __init__(self, parent, **kwargs): labels.append(kwargs)
        def pack(self, **kwargs): pass
    pages = {}
    integration.install_account_page(pages, SimpleNamespace(Label=Label), object(), {'window': '#fff', 'text': '#000'}, 'Arial', 'not-a-url', lambda zh, en: en, lambda: ('wrap', 'body'))
    assert pages == {'账号': 'wrap'}
    assert 'Check the Gateway URL' in labels[0]['text']
    assert not list(tmp_path.iterdir())


def test_saved_account_navigation_does_not_touch_account_or_node_state(tmp_path, monkeypatch):
    import json
    state = tmp_path / 'ui.json'
    state.write_text(json.dumps({'last_page': '常规'}))
    untouched = [tmp_path / 'account-session.json', tmp_path / 'node-config.json']
    for path in untouched:
        path.write_text('{"synthetic":"kept"}')
    monkeypatch.setattr(settings_helpers, 'UI_STATE_FILE', state)
    monkeypatch.setattr(settings_helpers, 'CONFIG_DIR', tmp_path)
    monkeypatch.delenv('LUCAS_SETTINGS_PAGE', raising=False)
    settings_helpers._save_last_page('账号')
    assert settings_helpers._load_last_page() == '账号'
    # Existing helper stores only page state, so it must not touch account/Node files.
    assert all(path.read_text() == '{"synthetic":"kept"}' for path in untouched)
    assert sorted(p.name for p in tmp_path.iterdir()) == ['account-session.json', 'node-config.json', 'ui.json']
    monkeypatch.setenv('LUCAS_SETTINGS_PAGE', '网络')
    assert settings_helpers._load_last_page() == '网络'


def test_all_new_settings_runtime_modules_participate_in_restart_detection():
    required = {'settings_account_integration.py', 'settings_account_ui.py',
                'settings_account_lifecycle.py', 'settings_navigation.py',
                'settings_helpers.py', 'local_account.py', 'local_account_state.py', 'credential_vault.py'}
    assert required <= set(InAppUpdater.SETTINGS_RUNTIME_FILES)
    root = Path(__file__).resolve().parents[1] / 'src' / 'gpt_windows_connector'
    assert all((root / name).is_file() for name in required)
