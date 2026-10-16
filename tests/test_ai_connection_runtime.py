"""Preserve the extracted AI UI contracts using in-memory dependencies only.

No HTTP calls, OAuth operations, clipboard writes or browser navigation occur.
Actual production fragments are executed; dispatched effects are not simulated
as permission grants or claimed as deployed acceptance.
"""
from __future__ import annotations

import json
import shutil
import subprocess

from gpt_windows_connector.web_ai_connection_runtime import (
    AI_CONNECTION_ACTION_SCRIPT,
    AI_CONNECTION_RENDER_SCRIPT,
)
from gpt_windows_connector.web_core_runtime import CORE_SCRIPT
from gpt_windows_connector.web_dashboard_read_runtime import DASHBOARD_INVALIDATION_SCRIPT


def test_ai_connection_fragments_have_one_composed_owner():
    assert CORE_SCRIPT.count(AI_CONNECTION_RENDER_SCRIPT) == 1
    assert CORE_SCRIPT.count(AI_CONNECTION_ACTION_SCRIPT) == 1
    for name in (
        "renderAiClients", "copyMcpUrl", "openAiModal", "updateAiHelp",
        "editAiConnection", "saveAiConnection", "deleteAiConnection",
    ):
        assert CORE_SCRIPT.count(f"function {name}(") == 1
    # Preserve the existing positions used by full-page and sliced UI fixtures.
    assert CORE_SCRIPT.index(AI_CONNECTION_RENDER_SCRIPT) < CORE_SCRIPT.index("let managedNodeId=")
    assert CORE_SCRIPT.index("async function loadNodeLogs(") < CORE_SCRIPT.index(AI_CONNECTION_ACTION_SCRIPT)
    assert CORE_SCRIPT.index(AI_CONNECTION_ACTION_SCRIPT) < CORE_SCRIPT.index("function openConnectModal(")


def test_ai_connection_runtime_contracts(tmp_path):
    node = shutil.which("node")
    assert node, "Node.js is required for AI connection runtime contracts"
    script = tmp_path / "ai-connection-runtime.mjs"
    script.write_text(
        "const runtime=" + json.dumps(DASHBOARD_INVALIDATION_SCRIPT + AI_CONNECTION_RENDER_SCRIPT + AI_CONNECTION_ACTION_SCRIPT) + ";\n" + CASES,
        encoding="utf-8",
    )
    result = subprocess.run(
        [node, "--test", str(script)], capture_output=True, text=True,
        encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "fail 0" in result.stdout


CASES = r'''
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

function fixture(){
  const calls=[],toasts=[],timers=[],prompts=[],clipboard=[],fallback=[],closed=[];
  let clipboardFailure=false,answer=true,refreshes=0,refreshFailure=null;
  const ctx={console,encodeURIComponent,decodeURIComponent,location:{href:'/dashboard'},
    loginGeneration:0,state:{user:{id:'synthetic-user'},aiClients:[],billing:null},
    esc:value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;'),
    timefmt:value=>'date:'+value,
    toast:value=>toasts.push(value),
    setTimeout:(fn,delay)=>{timers.push({fn,delay});return timers.length},
    navigator:{clipboard:{writeText:async value=>{clipboard.push(value);if(clipboardFailure)throw new Error('clipboard unavailable')}}},
    document:{execCommand:value=>fallback.push(value),getElementById:id=>ctx[id]||null,addEventListener(){}},
    closeModal:id=>{closed.push(id);ctx[id].classList.add('hidden')},
    refresh:async()=>{refreshes++;if(refreshFailure)throw new Error(refreshFailure)},
    api:(url,options={})=>{
      assert.match(url,/^\/api\/ai-connections\/[^/]+$/);
      assert.ok(['PUT','DELETE'].includes(options.method));
      return new Promise((resolve,reject)=>calls.push({url,options,resolve,reject}));
    }};
  ctx.window={confirm:text=>{prompts.push(text);return answer}};
  for(const name of ['aiClientTable','mcpUrl','aiModal','aiModalUrl','aiClientType','aiHelp','aiManageName','aiManageNote','aiManageModal','aiManageSave','metricAiClients']){
    const classes=new Set(['hidden']);
    ctx[name]={value:'',textContent:'',innerHTML:'',focused:false,selected:false,disabled:false,setAttribute(){},
      focus(){this.focused=true},select(){this.selected=true},
      classList:{contains:c=>classes.has(c),add:c=>classes.add(c),remove:c=>classes.delete(c)}};
  }
  vm.createContext(ctx);vm.runInContext(runtime,ctx);
  return {ctx,calls,toasts,timers,prompts,clipboard,fallback,closed,
    call:code=>vm.runInContext(code,ctx),
    clipboardFails:()=>{clipboardFailure=true},confirm:value=>{answer=value},
    refreshFails:value=>{refreshFailure=value},refreshes:()=>refreshes,
    tick:delay=>timers.filter(t=>t.delay===delay).forEach(t=>t.fn()),
    settle:(i,body={})=>calls[i].resolve(body),fail:(i,message)=>calls[i].reject(new Error(message))};
}
function client(extra={}){return {client_id:'client /a?+',client_name:'Original name',display_name:'Display name',note:'Saved note',created_at:'2026-10-16',...extra}}
function edit(f,c=client()){f.ctx.state.aiClients=[c];f.ctx.editAiConnection(encodeURIComponent(c.client_id));return c}
const shown=e=>!e.classList.contains('hidden');

test('empty AI list keeps its existing empty state',()=>{
  const f=fixture();f.ctx.renderAiClients();assert.equal(f.ctx.aiClientTable.innerHTML,'<div class="empty">No OAuth clients registered yet.</div>');assert.equal(f.calls.length,0);
});
test('AI rows retain escaping, dates and encoded edit/delete targets',()=>{
  const f=fixture(),c=client({display_name:'<Display & "name">',note:'<private & note>'});
  f.ctx.state.aiClients=[c];f.ctx.renderAiClients();const html=f.ctx.aiClientTable.innerHTML;
  assert.ok(html.includes('&lt;Display &amp; &quot;name&quot;&gt;'));assert.ok(html.includes('&lt;private &amp; note&gt;'));
  assert.ok(html.includes('date:2026-10-16'));assert.ok(html.includes("editAiConnection('"+encodeURIComponent(c.client_id)+"')"));
  assert.ok(html.includes("deleteAiConnection('"+encodeURIComponent(c.client_id)+"')"));assert.equal(f.calls.length,0);
});
for(const [display,name,expected] of [['','Named client','Named client'],['','','MCP Client']])test('name/note fallback: '+expected,()=>{
  const f=fixture();f.ctx.state.aiClients=[client({display_name:display,client_name:name,note:''})];f.ctx.renderAiClients();
  assert.ok(f.ctx.aiClientTable.innerHTML.includes('<b>'+expected+'</b>'));assert.ok(f.ctx.aiClientTable.innerHTML.includes('<td>—</td>'));
});
for(const fallback of [false,true])test('MCP URL copy retains clipboard fallback='+fallback,async()=>{
  const f=fixture();if(fallback)f.clipboardFails();await f.ctx.copyMcpUrl();
  assert.equal(f.ctx.mcpUrl.value,'https://lucasmcp.com/mcp');assert.deepEqual(f.clipboard,['https://lucasmcp.com/mcp']);
  assert.equal(f.ctx.mcpUrl.selected,fallback);assert.deepEqual(f.fallback,fallback?['copy']:[]);assert.deepEqual(f.toasts,['MCP URL copied']);assert.equal(f.calls.length,0);
});
for(const billing of [null,{ai_account_limit:3}])test('new AI setup within limit, billing='+JSON.stringify(billing),()=>{
  const f=fixture();f.ctx.state.billing=billing;f.ctx.state.aiClients=[client()];f.ctx.aiClientType.value='old draft';f.ctx.openAiModal();
  assert.ok(shown(f.ctx.aiModal));assert.equal(f.ctx.aiModalUrl.value,'https://lucasmcp.com/mcp');assert.equal(f.ctx.aiClientType.value,'');
  assert.equal(f.ctx.aiHelp.textContent,'Enter a name for the AI assistant you want to connect with Lucas.');assert.equal(f.ctx.aiClientType.focused,false);
  f.tick(50);assert.equal(f.ctx.aiClientType.focused,true);assert.equal(f.calls.length,0);
});
for(const limit of [0,1])test('at capacity retains existing delayed billing navigation, limit='+limit,()=>{
  const f=fixture();f.ctx.state.billing={ai_account_limit:limit};f.ctx.state.aiClients=limit?[client()]:[];f.ctx.aiClientType.value='preserved draft';f.ctx.openAiModal();
  assert.equal(shown(f.ctx.aiModal),false);assert.equal(f.ctx.aiClientType.value,'preserved draft');assert.equal(f.ctx.location.href,'/dashboard');
  assert.deepEqual(f.toasts,['AI account limit reached. Remove an unused AI connection.']);f.tick(500);assert.equal(f.ctx.location.href,'/billing');assert.equal(f.calls.length,0);
});
const help={
  chatgpt:'Create a custom MCP app, use the Lucas MCP URL, choose OAuth, then scan tools.',
  claude:'Add Lucas as a remote MCP connector and use OAuth when prompted.',
  gemini:'Add Lucas through an MCP-compatible integration and authorize with Lucas OAuth.',
  cursor:'Add a remote MCP server using the Lucas MCP URL and complete OAuth authorization.',
  codex:'Configure Lucas as a remote MCP server using the URL shown above.',
  'claude code':'Configure Lucas as a remote MCP server using the URL shown above.'};
for(const [name,expected] of Object.entries(help))test('existing setup help: '+name,()=>{
  const f=fixture();f.ctx.aiClientType.value=' '+name.toUpperCase()+' ';f.ctx.updateAiHelp();assert.equal(f.ctx.aiHelp.textContent,expected);assert.equal(f.calls.length,0);
});
for(const name of ['Custom AI','自定义助手','<assistant>'])test('custom setup name stays literal text: '+name,()=>{
  const f=fixture();f.ctx.aiClientType.value=' '+name+' ';f.ctx.updateAiHelp();assert.equal(f.ctx.aiHelp.textContent,'Add the Lucas MCP URL to '+name+' and complete OAuth authorization.');assert.equal(f.ctx.aiHelp.innerHTML,'');
});
test('empty setup help stays unchanged',()=>{
  const f=fixture();f.ctx.aiClientType.value='  ';f.ctx.updateAiHelp();assert.equal(f.ctx.aiHelp.textContent,'Enter a name for the AI assistant you want to connect with Lucas.');
});
test('edit decodes the target and fills the existing modal',()=>{
  const f=fixture(),c=edit(f);assert.equal(f.call('managedAiClientId'),c.client_id);assert.ok(shown(f.ctx.aiManageModal));
  assert.equal(f.ctx.aiManageName.value,c.display_name);assert.equal(f.ctx.aiManageNote.value,c.note);f.tick(50);assert.equal(f.ctx.aiManageName.focused,true);assert.equal(f.calls.length,0);
});
for(const [name,expected] of [['Fallback','Fallback'],['','MCP Client']])test('edit fallbacks: '+expected,()=>{
  const f=fixture();edit(f,client({display_name:'',client_name:name,note:''}));assert.equal(f.ctx.aiManageName.value,expected);assert.equal(f.ctx.aiManageNote.value,'');
});
test('missing edit target does not show or overwrite the modal',()=>{
  const f=fixture();f.ctx.aiManageName.value='untouched';f.ctx.editAiConnection('missing');assert.equal(shown(f.ctx.aiManageModal),false);assert.equal(f.ctx.aiManageName.value,'untouched');assert.equal(f.calls.length,0);
});
test('save without a selection makes no request',async()=>{
  const f=fixture();await f.ctx.saveAiConnection();assert.equal(f.calls.length,0);assert.equal(f.refreshes(),0);
});
test('save dispatches exact captured target/trimmed payload and preserves refresh order',async()=>{
  const f=fixture(),c=edit(f);f.ctx.aiManageName.value='  Updated name  ';f.ctx.aiManageNote.value='  新备注  ';const p=f.ctx.saveAiConnection();
  assert.equal(f.calls.length,1);assert.equal(f.calls[0].url,'/api/ai-connections/'+encodeURIComponent(c.client_id));assert.equal(f.calls[0].options.method,'PUT');
  assert.deepEqual(JSON.parse(f.calls[0].options.body),{display_name:'Updated name',note:'新备注'});assert.equal(f.refreshes(),0);assert.ok(shown(f.ctx.aiManageModal));
  assert.equal(JSON.parse(f.calls[0].options.body).display_name,'Updated name');f.settle(0);await p;
  assert.equal(shown(f.ctx.aiManageModal),false);assert.equal(f.refreshes(),1);assert.deepEqual(f.toasts,['AI connection saved']);
});
test('save failure preserves the modal and shows the error',async()=>{
  const f=fixture();edit(f);const p=f.ctx.saveAiConnection();f.fail(0,'Synthetic save failure');await p;assert.ok(shown(f.ctx.aiManageModal));assert.deepEqual(f.closed,[]);assert.equal(f.refreshes(),0);assert.deepEqual(f.toasts,['Synthetic save failure']);
});
test('post-save refresh failure remains visible without retrying the PUT',async()=>{
  const f=fixture();edit(f);f.refreshFails('Synthetic refresh failure');const p=f.ctx.saveAiConnection();f.settle(0);await p;assert.equal(f.calls.length,1);assert.equal(f.refreshes(),1);assert.deepEqual(f.toasts,['Synthetic refresh failure']);
});
for(const id of ['', 'missing'])test('unknown delete target is rejected: '+JSON.stringify(id),async()=>{
  const f=fixture();f.ctx.state.aiClients=[client()];await f.ctx.deleteAiConnection(id);assert.equal(f.prompts.length,0);assert.equal(f.calls.length,0);assert.deepEqual(f.toasts,['AI connection not found. Refresh and try again.']);
});
test('declining delete preserves the client and makes no request',async()=>{
  const f=fixture(),c=client();f.ctx.state.aiClients=[c];f.confirm(false);await f.ctx.deleteAiConnection(encodeURIComponent(c.client_id));
  assert.equal(f.prompts[0],'Delete AI connection Display name?\n\nThis removes the Lucas OAuth connection. You can reconnect it later.');assert.equal(f.calls.length,0);assert.equal(f.ctx.state.aiClients[0],c);
});
test('accepted delete uses the same target and updates only the existing list/metric',async()=>{
  const f=fixture(),c=client(),other=client({client_id:'other'});f.ctx.state.aiClients=[c,other];const p=f.ctx.deleteAiConnection(encodeURIComponent(c.client_id));
  assert.equal(f.calls.length,1);assert.equal(f.calls[0].url,'/api/ai-connections/'+encodeURIComponent(c.client_id));assert.equal(f.calls[0].options.method,'DELETE');assert.equal('body' in f.calls[0].options,false);
  assert.equal(f.ctx.state.aiClients.length,2);f.settle(0);await p;assert.deepEqual(f.ctx.state.aiClients,[other]);assert.equal(f.ctx.metricAiClients.textContent,1);assert.equal(f.refreshes(),0);assert.deepEqual(f.toasts,['AI connection deleted']);
});
test('delete failure leaves current clients intact',async()=>{
  const f=fixture(),c=client();f.ctx.state.aiClients=[c];const p=f.ctx.deleteAiConnection(encodeURIComponent(c.client_id));f.fail(0,'Synthetic delete failure');await p;
  assert.equal(f.ctx.state.aiClients[0],c);assert.equal(f.ctx.state.aiClients.length,1);assert.deepEqual(f.toasts,['Synthetic delete failure']);assert.equal(f.refreshes(),0);
});
'''
