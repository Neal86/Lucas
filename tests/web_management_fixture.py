"""Actual composed dashboard with synthetic mutation/read transport for UI tests."""
from __future__ import annotations

import json
import re
import shutil
import subprocess

from gpt_windows_connector import server
from test_dashboard_response_ownership import DASHBOARD_CASES, DashboardIds


def run_management_cases(tmp_path, cases, name):
    html = server.webapp._dashboard_html()
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S)
    runtime = next(s for s in scripts if "const state=" in s)
    assert runtime.endswith("\nboot();\n")
    runtime = next(s for s in scripts if "const WEB_LANG=" in s) + "\n" + runtime[:-len("boot();\n")]
    ids = DashboardIds(); ids.feed(html)
    fixture = DASHBOARD_CASES.split("for(const language of ['en','zh-CN']){")[0]
    start = fixture.index("  ctx.fetch="); end = fixture.index("  vm.createContext", start)
    fixture = fixture[:start] + r'''
  const confirmations=[];ctx.confirm=message=>{confirmations.push(message);return true};
  ctx.fetch=(url,options)=>{
    assert.equal(options.credentials,'include');assert.equal(options.signal,undefined);
    const read=['/api/nodes','/api/logs?limit=20','/api/ai-connections','/auth/me'].includes(url)||/^\/api\/nodes\/[^/]+\/logs\?limit=250$/.test(url);
    const write=/^\/api\/(?:nodes\/[^/]+\/(?:name|activate)|ai-connections\/[^/]+)$/.test(url);
    assert.ok(read&&!options.method||write&&['PUT','POST','DELETE'].includes(options.method),'Unexpected synthetic request '+url);
    return new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}));
  };
''' + fixture[end:]
    fixture = fixture.replace("return {ctx,requests,elements,", "return {ctx,requests,confirmations,elements,")
    file = tmp_path / (name + ".mjs")
    file.write_text("const runtime=" + json.dumps(runtime) + ";\nconst markup=" + json.dumps(ids.elements) + ";\n" + fixture + HELPERS + cases, encoding="utf-8")
    node = shutil.which("node"); assert node, "Node.js is required for management regressions"
    result = subprocess.run([node, "--test", str(file)], capture_output=True, text=True, encoding="utf-8", timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "fail 0" in result.stdout


HELPERS = r'''
const managementTest=(name,body)=>test(name,{timeout:1500},body);
function seedNodes(f){f.call("state.nodes=[{node_id:'a /?',name:'A',authorized:true,allowed_roots:['SYNTHETIC-A']},{node_id:'b',name:'B',authorized:true,allowed_roots:['SYNTHETIC-B']}];renderNodes()")}
function openNode(f,id='a /?'){f.call('openNodeModal('+JSON.stringify(encodeURIComponent(id))+')')}
function account(f){f.call("showAuth();state.user={id:'user-b',email:'b@example.test',role:'user'};showApp()")}
function seedClients(f){f.call("state.aiClients=[{client_id:'shared /?',display_name:'First'},{client_id:'other',display_name:'Second'}];renderAiClients()")}
function deleteClient(f,id='shared /?'){return f.call('deleteAiConnection('+JSON.stringify(encodeURIComponent(id))+')')}
function ownerChange(f,kind){
 if(kind==='account')account(f);
 else if(kind==='direct-user')f.call("state.user={id:'user-b',email:'b@example.test',role:'user'}");
 else if(kind==='login-generation')f.call('loginGeneration++');
 else if(kind==='navigation')f.call("view('account',null)");
 else if(kind==='history'){f.ctx.location.pathname='/account';f.call('routeFromLocation()')}
 else if(kind==='auth')f.call('showAuth()');
}
async function respondOutcome(f,index,outcome,body={}){
 if(outcome==='network')f.requests[index].reject(new Error('OLD_ERROR'));
 else f.respond(index,outcome===200?body:{error:'OLD_ERROR'},outcome);
 await settle();
}
'''
