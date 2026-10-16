"""Execute the shipped popup script with deterministic DOM/Chrome boundaries.

These are runtime regressions, not a substitute for the opt-in Chromium suite.
LUCAS_POPUP_DIR can target an unchanged archived checkout for baseline checks.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest


POPUP_DIR = Path(__file__).resolve().parents[1] / "extensions" / "lucas-browser"
RUNTIME = r"""
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const tests=new Map();
const test=(name,run)=>tests.set(name,run);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const unhandled=[];
process.on('unhandledRejection',error=>unhandled.push(String(error)));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};

class Element {
  constructor(tag,attributes={}) {
    this.tagName=tag.toUpperCase();this.attributes=attributes;
    this.value=attributes.value||'';this.textContent='';this.children=[];this.disabled=false;
  }
  replaceChildren(...children) {
    this.children=children;
    if(this.tagName==='SELECT') this.value=children[0]?.value||'';
  }
  set innerHTML(value) {throw Error('Popup must render feedback as text, not HTML');}
}

async function popup({initialStatus}={}) {
  const html=fs.readFileSync(path.join(process.argv[1],'popup.html'),'utf8');
  const elements=new Map();
  for(const match of html.matchAll(/<([a-z][a-z0-9]*)\b([^>]*\bid="([^"]+)"[^>]*)>/gi)) {
    const attributes=Object.fromEntries([...match[2].matchAll(/([\w-]+)="([^"]*)"/g)].map(x=>[x[1],x[2]]));
    elements.set(match[3],new Element(match[1],attributes));
  }
  const h={elements,calls:[],queries:[],intervals:[],timeouts:[],handlers:new Map(),
    state:{status:'Paired',owners:[{user_id:'owner-a',name:'Alice'},{user_id:'owner-b',email:'b@example.test'}],
      sessions:[{session_id:'ext-one',title:'Fixture tab'}],can_grant:true},
    query:async()=>[{id:7}],
    get:id=>elements.get(id),
    error:()=>{
      assert.ok(elements.has('action-error'),'Popup needs a separate persistent action-error region');
      return elements.get('action-error').textContent;
    },
  };
  if(initialStatus) h.handlers.set('status',initialStatus);
  const context=vm.createContext({
    document:{getElementById:id=>elements.get(id)||null,createElement:tag=>new Element(tag)},
    chrome:{
      runtime:{sendMessage:async message=>{
        h.calls.push(JSON.parse(JSON.stringify(message)));
        const handler=h.handlers.get(message.type);
        return handler?handler(message):message.type==='status'?h.state:{ok:true};
      }},
      tabs:{query:async options=>{h.queries.push(JSON.parse(JSON.stringify(options)));return h.query(options);}},
    },
    setInterval:(fn,ms)=>{h.intervals.push({fn,ms});return h.intervals.length;},
    setTimeout:(fn,ms)=>{h.timeouts.push({fn,ms});return h.timeouts.length;},
  });
  vm.runInContext(fs.readFileSync(path.join(process.argv[1],'popup.js'),'utf8'),context,{filename:'popup.js'});
  h.click=async id=>{await h.get(id).onclick();await flush();};
  h.poll=async()=>{for(const timer of h.intervals) await timer.fn();await flush();};
  h.delays=async()=>{for(const timer of h.timeouts.splice(0)) await timer.fn();await flush();};
  await flush();
  return h;
}

test('action error is an accessible text-only live region',async()=>{
  const h=await popup();
  assert.ok(h.get('action-error'),'Missing action error region');
  assert.equal(h.get('action-error').attributes.role,'alert');
  assert.equal(h.get('action-error').attributes['aria-atomic'],'true');
  h.handlers.set('pair',()=>({error:'<img src=x onerror=alert(1)>'}));
  await h.click('connect');
  assert.match(h.error(),/<img src=x onerror=alert\(1\)>/);
});

test('rejected pair preserves input and persists across status polling',async()=>{
  const h=await popup();h.get('token').value='invalid-test-token';h.get('port').value='999';
  h.handlers.set('pair',()=>({error:'Invalid token or port'}));
  await h.click('connect');
  assert.equal(h.get('token').value,'invalid-test-token');
  assert.match(h.error(),/Invalid token or port/);
  await h.poll();await h.poll();
  assert.match(h.error(),/Invalid token or port/);
  assert.equal(h.get('status').textContent,'Paired');
  assert.deepEqual(h.calls.find(x=>x.type==='pair'),{type:'pair',token:'invalid-test-token',port:999});
});

test('pair transport rejection preserves input and is handled',async()=>{
  const h=await popup();h.get('token').value='synthetic-token';
  h.handlers.set('pair',()=>{throw Error('Extension channel closed');});
  await h.click('connect');
  assert.equal(h.get('token').value,'synthetic-token');
  assert.match(h.error(),/Extension channel closed/);
  await h.poll();assert.match(h.error(),/Extension channel closed/);
});

test('successful pairing retry clears error but does not claim authentication',async()=>{
  const h=await popup();h.get('token').value='synthetic-token';
  h.handlers.set('pair',()=>({error:'Invalid token or port'}));await h.click('connect');
  h.handlers.set('pair',()=>({ok:true}));
  h.state={status:'Connecting',owners:[],sessions:[],can_grant:false};
  await h.click('connect');
  assert.equal(h.error(),'');assert.equal(h.get('token').value,'');
  assert.equal(h.get('status').textContent,'Connecting');assert.equal(h.get('grant').disabled,true);
  h.state.status='Disconnected — permissions revoked';await h.poll();
  assert.equal(h.get('status').textContent,'Disconnected — permissions revoked');
  assert.equal(h.get('grant').disabled,true);
});

test('missing action confirmation is not treated as success',async()=>{
  const h=await popup();h.get('token').value='synthetic-token';
  h.handlers.set('pair',()=>undefined);await h.click('connect');
  assert.equal(h.get('token').value,'synthetic-token');assert.match(h.error(),/confirmation/i);
  h.handlers.set('revoke',()=>({ok:false}));await h.click('revoke');
  assert.match(h.error(),/Revocation failed/);
});

test('grant response rejection persists across scheduled and periodic refresh',async()=>{
  const h=await popup();h.get('owner').value='owner-b';
  h.handlers.set('grant',()=>({error:'Tab authorization was cancelled'}));
  await h.click('grant');
  assert.deepEqual(h.queries,[{active:true,currentWindow:true}]);
  assert.deepEqual(h.calls.find(x=>x.type==='grant'),{type:'grant',owner_id:'owner-b',tab_id:7});
  assert.match(h.error(),/Tab authorization was cancelled/);
  await h.delays();await h.poll();
  assert.match(h.error(),/Tab authorization was cancelled/);
});

test('grant transport rejection is handled',async()=>{
  const h=await popup();h.handlers.set('grant',()=>{throw Error('Grant channel unavailable');});
  await h.click('grant');assert.match(h.error(),/Grant channel unavailable/);
});

test('tab lookup rejection is handled without sending grant',async()=>{
  const h=await popup();h.query=async()=>{throw Error('Cannot query active tab');};
  await h.click('grant');assert.match(h.error(),/Cannot query active tab/);
  assert.equal(h.calls.filter(x=>x.type==='grant').length,0);
});

test('missing active tab is actionable and never dispatches grant',async()=>{
  const h=await popup();
  for(const tabs of [[],[{}],[{id:-1}]]) {
    h.query=async()=>tabs;await h.click('grant');
    assert.match(h.error(),/No active tab/);
  }
  assert.equal(h.calls.filter(x=>x.type==='grant').length,0);
});

test('revoke response rejection and transport rejection remain visible',async()=>{
  const h=await popup();h.handlers.set('revoke',()=>({error:'Revocation rejected'}));
  await h.click('revoke');assert.match(h.error(),/Revocation rejected/);
  await h.poll();assert.match(h.error(),/Revocation rejected/);
  h.handlers.set('revoke',()=>{throw Error('Revoke channel unavailable');});
  await h.click('revoke');assert.match(h.error(),/Revoke channel unavailable/);
  await h.poll();assert.match(h.error(),/Revoke channel unavailable/);
});

test('successful grant and revoke clear prior errors and refresh sessions',async()=>{
  const h=await popup();h.handlers.set('grant',()=>({error:'First attempt failed'}));
  await h.click('grant');assert.match(h.error(),/First attempt failed/);
  h.handlers.delete('grant');await h.click('grant');
  assert.equal(h.error(),'');assert.equal(h.get('status').textContent,'Authorization requested');
  h.state.status='Tab authorized';await h.delays();assert.equal(h.get('status').textContent,'Tab authorized');
  h.handlers.set('pair',()=>({error:'Invalid token or port'}));await h.click('connect');
  h.state.sessions=[];h.state.status='Permissions revoked';await h.click('revoke');
  assert.equal(h.error(),'');assert.equal(h.get('status').textContent,'Permissions revoked');
  assert.equal(h.get('sessions').children.length,0);
});

test('accepted pair clears submitted input and displays only bridge status',async()=>{
  const h=await popup();h.get('token').value='fixture-token-accepted-by-background';h.get('port').value='8767';
  h.state={status:'Connecting',owners:[],sessions:[],can_grant:false};
  await h.click('connect');
  assert.deepEqual(h.calls.find(x=>x.type==='pair'),{type:'pair',token:'fixture-token-accepted-by-background',port:8767});
  assert.equal(h.get('token').value,'');assert.equal(h.get('status').textContent,'Connecting');
  assert.equal(h.get('grant').disabled,true);
});

test('valid grant and revoke preserve message contracts and refresh status',async()=>{
  const h=await popup();h.get('owner').value='owner-b';await h.click('grant');
  assert.deepEqual(h.calls.find(x=>x.type==='grant'),{type:'grant',owner_id:'owner-b',tab_id:7});
  assert.equal(h.get('status').textContent,'Authorization requested');
  h.state.status='Tab authorized';await h.delays();assert.equal(h.get('status').textContent,'Tab authorized');
  h.state.status='Permissions revoked';h.state.sessions=[];await h.click('revoke');
  assert.deepEqual(h.calls.find(x=>x.type==='revoke'),{type:'revoke'});
  assert.equal(h.get('status').textContent,'Permissions revoked');assert.equal(h.get('sessions').children.length,0);
});

test('polling retains owner selection session rendering and grant gating',async()=>{
  const h=await popup();assert.deepEqual(h.intervals.map(x=>x.ms),[1000]);
  assert.equal(h.get('owner').value,'owner-a');assert.equal(h.get('grant').disabled,false);
  assert.equal(h.get('sessions').children[0].textContent,'Fixture tab — ext-one');
  h.get('owner').value='owner-b';await h.poll();assert.equal(h.get('owner').value,'owner-b');
  h.state.can_grant=false;await h.poll();assert.equal(h.get('grant').disabled,true);
  h.state.can_grant=true;h.state.owners=[{user_id:'owner-c'}];h.state.sessions=[{session_id:'ext-two'}];
  await h.poll();assert.equal(h.get('owner').value,'owner-c');assert.equal(h.get('grant').disabled,false);
  assert.equal(h.get('sessions').children[0].textContent,'Tab — ext-two');
  h.state.owners=[];await h.poll();assert.equal(h.get('grant').disabled,true);
});

test('successful pair leaves newly edited input untouched',async()=>{
  const h=await popup();const pending=deferred();h.get('token').value='submitted-token';
  h.handlers.set('pair',()=>pending.promise);const click=h.click('connect');
  h.get('token').value='newly-typed-token';pending.resolve({ok:true});await click;
  assert.equal(h.get('token').value,'newly-typed-token');
});

test('late action completion cannot erase newer rejection or typed input',async()=>{
  const h=await popup();const pending=deferred();h.get('token').value='same-token';
  h.handlers.set('pair',()=>pending.promise);const first=h.click('connect');
  h.handlers.set('pair',()=>({error:'Newer pairing rejected'}));await h.click('connect');
  pending.resolve({ok:true});await first;
  assert.equal(h.get('token').value,'same-token');assert.match(h.error(),/Newer pairing rejected/);
});

test('late rejected action cannot overwrite successful newer action',async()=>{
  const h=await popup();const pending=deferred();h.handlers.set('grant',()=>pending.promise);
  const first=h.click('grant');await flush();h.state.status='Permissions revoked';await h.click('revoke');
  pending.resolve({error:'Stale grant failure'});await first;
  assert.equal(h.error(),'');assert.equal(h.get('status').textContent,'Permissions revoked');
});

test('revoke supersedes a pending tab query before it can send grant',async()=>{
  const h=await popup();const pending=deferred();h.query=()=>pending.promise;
  const grant=h.click('grant');await h.click('revoke');pending.resolve([{id:7}]);await grant;
  assert.equal(h.calls.filter(x=>x.type==='grant').length,0);assert.equal(h.error(),'');
});

test('status transport and malformed responses do not erase action errors',async()=>{
  const h=await popup();h.handlers.set('pair',()=>({error:'Keep this action error'}));await h.click('connect');
  for(const response of [()=>{throw Error('Worker unavailable');},()=>({error:'Status unavailable'}),()=>undefined,()=>({})]) {
    h.handlers.set('status',response);await h.poll();
    assert.match(h.get('status').textContent,/Unable to refresh status/);
    assert.match(h.error(),/Keep this action error/);assert.equal(h.get('grant').disabled,true);
  }
  h.handlers.delete('status');await h.poll();
  assert.equal(h.get('grant').disabled,false);assert.match(h.error(),/Keep this action error/);
});

test('initial status failure is caught and later polling recovers',async()=>{
  const h=await popup({initialStatus:()=>{throw Error('Worker is waking');}});
  assert.match(h.get('status').textContent,/Worker is waking/);assert.equal(h.get('grant').disabled,true);
  h.handlers.delete('status');await h.poll();assert.equal(h.get('status').textContent,'Paired');
});

test('successful action remains successful when its refresh fails',async()=>{
  const h=await popup();h.handlers.set('revoke',()=>({error:'First revocation failed'}));await h.click('revoke');
  h.handlers.delete('revoke');h.handlers.set('status',()=>{throw Error('Status temporarily unavailable');});
  await h.click('revoke');assert.equal(h.error(),'');
  assert.match(h.get('status').textContent,/Unable to refresh status/);
});

test('out of order refresh cannot restore stale connection state',async()=>{
  const h=await popup();const pending=deferred();h.handlers.set('status',()=>pending.promise);
  const stale=h.poll();await flush();h.handlers.delete('status');
  h.state={status:'Disconnected',owners:[],sessions:[],can_grant:false};await h.poll();
  pending.resolve({status:'Paired',owners:[{user_id:'stale-owner'}],sessions:[],can_grant:true});await stale;
  assert.equal(h.get('status').textContent,'Disconnected');assert.equal(h.get('grant').disabled,true);
  assert.equal(h.get('owner').children.length,0);
});

test('stale refresh failure cannot overwrite newer refresh or action',async()=>{
  const h=await popup();const pending=deferred();h.handlers.set('status',()=>pending.promise);
  const stale=h.poll();await flush();h.handlers.delete('status');await h.click('grant');
  pending.reject(Error('Old status failure'));await stale;
  assert.equal(h.get('status').textContent,'Authorization requested');assert.equal(h.get('grant').disabled,false);
});

(async()=>{
  const run=tests.get(process.argv[2]);assert.ok(run,'Unknown popup test');
  await run();await flush();await flush();
  assert.deepEqual(unhandled,[],'Popup leaked an unhandled promise rejection');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
CASES = re.findall(r"^test\('([^']+)'", RUNTIME, flags=re.MULTILINE)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for popup runtime tests")
@pytest.mark.parametrize("case", CASES)
def test_extension_popup_runtime(case):
    directory = os.environ.get("LUCAS_POPUP_DIR", str(POPUP_DIR))
    result = subprocess.run(
        [shutil.which("node"), "-e", RUNTIME, directory, case],
        text=True, capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
