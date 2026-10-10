from pathlib import Path
import asyncio
import json
import shutil
import subprocess
import pytest
from gpt_windows_connector import browser_router

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / 'src/gpt_windows_connector/browser_bridge_extension'

def test_extension_worker_runtime():
    if not shutil.which('node'): pytest.skip('Node.js unavailable')
    result = subprocess.run(['node', str(ROOT/'tests/browser_extension_runtime.cjs'), str(EXT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr

def test_extension_manifest_assets_exist_and_optional_data_permissions():
    manifest = json.loads((EXT/'manifest.json').read_text())
    assert manifest['version'] == '2.0.0'
    assert 'debugger' in manifest['permissions']
    assert manifest['optional_permissions'] == ['history','bookmarks']
    assets=[manifest['background']['service_worker'], manifest['side_panel']['default_path'],manifest['options_page'],manifest['action']['default_popup'],*manifest['icons'].values(),*manifest['content_scripts'][0]['js']]
    for asset in assets: assert (EXT/asset).is_file()
    assert manifest['content_scripts'][0]['all_frames']

def test_bridge_uses_stable_tab_id():
    with pytest.raises(ValueError, match='tab_id'): browser_router._bridge_params('snapshot',{'page_index':0})
    assert browser_router._bridge_params('snapshot',{'tab_id':7})['tab_id']==7

def test_browser_controls_route_to_extension():
    for operation in ('screenshot','frames','extract','assets','selection','double_click','drag','console','cdp','evaluate','history_search','bookmarks_search','download_status'):
        assert operation in browser_router.BRIDGE_OPERATION_MAP

def test_extension_handoff_reaches_chat_without_being_wrapped(monkeypatch):
    monkeypatch.setattr(browser_router,'_binding_for_action',lambda *args:({'transport':'bridge','bridge_installation_id':'test','task_key':'task'}, {'profile_key':'selected'}))
    class Bridge:
        async def request(self,*args,**kwargs):
            return {'requires_user_action':True,'action_type':'website_permission','chat_message':'Allow example.com'}
    monkeypatch.setattr(browser_router,'bridge_server',Bridge())
    result=asyncio.run(browser_router.profile_action({'operation':'snapshot','operation_params':{'tab_id':1}},None,None))
    assert result['requires_user_action'] and result['chat_message']=='Allow example.com'
    assert 'result' not in result
