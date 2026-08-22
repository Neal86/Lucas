from __future__ import annotations

import json
import secrets
import sqlite3
import time
from urllib.parse import unquote

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Mount, Route

from . import gateway
from .admin import admin_routes


DASHBOARD_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Lucas</title>
<style>
:root{--bg:#f6f7fb;--card:#fff;--text:#101828;--muted:#667085;--line:#e4e7ec;--accent:#155eef;--ok:#079455;--danger:#d92d20;--shadow:0 1px 3px rgba(16,24,40,.08),0 1px 2px rgba(16,24,40,.05)}*{box-sizing:border-box}body{margin:0;font:14px/1.45 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--text);background:var(--bg)}button,input,select{font:inherit}.hidden{display:none!important}.auth{min-height:100vh;display:grid;place-items:center;padding:24px}.auth-card{width:min(440px,100%);background:var(--card);border:1px solid var(--line);border-radius:18px;padding:30px;box-shadow:var(--shadow)}h1,h2,h3,p{margin-top:0}.brand{font-size:23px;font-weight:750;margin-bottom:6px}.sub{color:var(--muted);margin-bottom:24px}.field{margin:14px 0}.field label{display:block;font-weight:600;margin-bottom:6px}.input,select{width:100%;border:1px solid #d0d5dd;border-radius:9px;padding:10px 12px;background:#fff;color:var(--text);outline:none}.input:focus,select:focus{border-color:#84adff;box-shadow:0 0 0 3px #d1e0ff}.btn{border:0;border-radius:9px;padding:10px 14px;font-weight:650;cursor:pointer}.primary{background:var(--accent);color:#fff}.secondary{background:#fff;color:#344054;border:1px solid #d0d5dd}.danger{background:#fff;color:var(--danger);border:1px solid #fda29b}.google{width:100%;background:#fff;border:1px solid #d0d5dd;color:#344054;margin-top:10px}.switch{color:var(--accent);background:none;border:0;padding:0;cursor:pointer}.error{background:#fef3f2;color:#b42318;border:1px solid #fecdca;padding:10px;border-radius:8px;margin:10px 0}.shell{min-height:100vh;display:grid;grid-template-columns:240px 1fr}.side{background:#101828;color:#fff;padding:22px 14px;display:flex;flex-direction:column;gap:6px}.logo{font-size:18px;font-weight:750;padding:0 10px 22px}.nav{background:transparent;color:#d0d5dd;border:0;text-align:left;padding:10px 12px;border-radius:8px;cursor:pointer}.nav.active,.nav:hover{background:#344054;color:#fff}.userbox{margin-top:auto;border-top:1px solid #344054;padding:15px 10px 0;color:#d0d5dd}.main{padding:28px;overflow:auto}.top{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;box-shadow:var(--shadow)}.metric{font-size:28px;font-weight:750}.muted{color:var(--muted)}.toolbar{display:flex;gap:8px;align-items:center;margin-bottom:14px}.toolbar .input,.toolbar select{width:auto}.table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden}.table th,.table td{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}.table th{font-size:12px;color:#475467;background:#f9fafb;text-transform:uppercase;letter-spacing:.03em}.badge{display:inline-flex;padding:3px 8px;border-radius:999px;font-size:12px;font-weight:650}.online{background:#ecfdf3;color:#027a48}.offline{background:#f2f4f7;color:#475467}.modal-backdrop{position:fixed;inset:0;background:rgba(16,24,40,.45);display:grid;place-items:center;padding:18px}.modal{width:min(620px,100%);max-height:88vh;overflow:auto;background:#fff;border-radius:14px;padding:22px;box-shadow:0 20px 40px rgba(16,24,40,.22)}.row{display:flex;gap:10px}.row>*{flex:1}.folderbox{border:1px solid var(--line);border-radius:10px;min-height:250px;max-height:360px;overflow:auto;margin-top:8px}.folder{display:flex;gap:10px;align-items:center;padding:10px 12px;border-bottom:1px solid #f2f4f7;cursor:pointer}.folder:hover{background:#f9fafb}.folder.selected{background:#eff4ff}.path{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;color:#475467;word-break:break-all}.actions{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}.empty{padding:28px;text-align:center;color:var(--muted)}pre.details{white-space:pre-wrap;max-width:560px;margin:0;font-size:12px}.log-filter{display:flex;gap:8px;margin-bottom:12px}.toast{position:fixed;right:22px;bottom:22px;background:#101828;color:#fff;padding:12px 16px;border-radius:9px;box-shadow:var(--shadow)}@media(max-width:850px){.shell{grid-template-columns:1fr}.side{position:sticky;top:0;z-index:5;flex-direction:row;overflow:auto;padding:10px}.logo,.userbox{display:none}.main{padding:16px}.grid{grid-template-columns:1fr}.row{flex-direction:column}.table{display:block;overflow:auto}}
</style>
</head>
<body>
<div id="auth" class="auth hidden"><div class="auth-card"><div class="brand">Lucas</div><div class="sub">Connect your AI clients to your Windows computers through your VPS.</div><div id="authError" class="error hidden"></div><div id="loginForm"><div class="field"><label>Email</label><input id="loginEmail" class="input" type="email" autocomplete="email"></div><div class="field"><label>Password</label><input id="loginPassword" class="input" type="password" autocomplete="current-password"></div><button class="btn primary" style="width:100%" onclick="login()">Sign in</button><button class="btn google" onclick="location.href='/auth/google/start'">Continue with Google</button><p class="muted" style="margin:16px 0 0">No account? <button class="switch" onclick="showRegister(true)">Create one</button></p></div><div id="registerForm" class="hidden"><div class="field"><label>Name</label><input id="regName" class="input"></div><div class="field"><label>Email</label><input id="regEmail" class="input" type="email"></div><div class="field"><label>Password</label><input id="regPassword" class="input" type="password" placeholder="At least 10 characters"></div><button class="btn primary" style="width:100%" onclick="registerUser()">Create account</button><button class="btn google" onclick="location.href='/auth/google/start'">Sign up with Google</button><p class="muted" style="margin:16px 0 0">Already registered? <button class="switch" onclick="showRegister(false)">Sign in</button></p></div></div></div>
<div id="app" class="shell hidden"><aside class="side"><div class="logo">Lucas</div><button class="nav active" data-view="dashboard" onclick="view('dashboard',this)">Dashboard</button><button class="nav" data-view="nodes" onclick="view('nodes',this)">Windows Nodes</button><button class="nav" data-view="ai" onclick="view('ai',this)">AI Connections</button><button class="nav" data-view="logs" onclick="view('logs',this)">Activity Logs</button><button class="nav" data-view="account" onclick="view('account',this)">Account & Security</button><button id="adminNav" class="nav hidden" data-view="admin" onclick="view('admin',this)">Admin</button><div class="userbox"><div id="userName"></div><small id="userEmail"></small><div style="margin-top:10px"><button class="btn secondary" onclick="logout()">Sign out</button></div></div></aside><main class="main"><div id="dashboard" class="view"><div class="top"><div><h2>Dashboard</h2><p class="muted">Your Windows computers, AI connections, and recent activity.</p></div></div><div class="grid"><div class="card"><div class="muted">Paired Windows nodes</div><div id="metricPairedNodes" class="metric">0</div></div><div class="card"><div class="muted">Online Windows nodes</div><div id="metricNodes" class="metric">0</div></div><div class="card"><div class="muted">AI clients</div><div id="metricAiClients" class="metric">0</div></div></div><div class="card" style="margin-top:16px"><h3>Recent activity</h3><div id="recentLogs"></div></div></div><div id="nodes" class="view hidden"><div class="top"><div><h2>Windows Nodes</h2><p class="muted">Download the Lucas pairing script, generate a code, and connect this Windows PC.</p></div><div style="display:flex;gap:8px"><a class="btn secondary" style="text-decoration:none" href="/download/Lucas-Node.bat">Download Lucas Node</a><button class="btn primary" onclick="openPairModal()">Pair computer</button></div></div><div id="nodeTable"></div></div><div id="ai" class="view hidden"><div class="top"><div><h2>AI Connections</h2><p class="muted">Connect multiple AI and MCP clients to the same Lucas account securely with OAuth.</p></div><button class="btn primary" onclick="openAiModal()">Add AI</button></div><div class="card"><div style="display:flex;justify-content:space-between;gap:16px;align-items:center;flex-wrap:wrap"><div><h3 style="margin-bottom:6px">Lucas MCP Gateway</h3><p class="muted" style="margin:0">OAuth 2.0 + PKCE · refresh tokens · dynamic client registration</p></div><span class="badge online">Ready</span></div><div class="field"><label>MCP Server URL</label><input id="mcpUrl" class="input" readonly value="https://lucas.autozon.xyz/mcp"></div><p class="muted">Use this same URL from ChatGPT, Claude, Gemini, Cursor, Codex, Claude Code, or any compatible MCP client. Each AI authorizes independently.</p><div class="toolbar"><button class="btn primary" onclick="openAiModal()">Add AI connection</button><button class="btn secondary" onclick="copyMcpUrl()">Copy MCP URL</button></div></div><div class="card" style="margin-top:16px"><h3>Registered AI / MCP clients</h3><div id="aiClientTable"><div class="empty">No OAuth clients registered yet.</div></div></div></div><div id="logs" class="view hidden"><div class="top"><div><h2>Activity Logs</h2><p class="muted">Only activity belonging to your account is shown.</p></div></div><div class="log-filter"><input id="logAction" class="input" placeholder="Action filter"><input id="logTarget" class="input" placeholder="Target"><button class="btn secondary" onclick="loadLogs()">Filter</button></div><div id="logTable"></div></div><div id="account" class="view hidden"><div class="top"><div><h2>Account & Security</h2><p class="muted">Authentication and connector security information.</p></div></div><div class="card"><h3 id="accountName"></h3><p id="accountEmail"></p><p class="muted">Authentication provider: <span id="accountProvider"></span></p><p class="muted">All AI-to-computer traffic is relayed through this VPS Gateway. Nodes do not require a public inbound port.</p></div></div><div id="admin" class="view hidden"><div class="top"><div><h2>Admin</h2><p class="muted">Lucas SaaS operations, users, usage, nodes, subscriptions, audit logs, and system health.</p></div></div><div class="toolbar" id="adminTabs"><button class="btn primary" onclick="adminTab('dashboard',this)">Dashboard</button><button class="btn secondary" onclick="adminTab('users',this)">Users</button><button class="btn secondary" onclick="adminTab('usage',this)">Usage</button><button class="btn secondary" onclick="adminTab('nodes',this)">Nodes</button><button class="btn secondary" onclick="adminTab('operations',this)">Operations</button><button class="btn secondary" onclick="adminTab('subscriptions',this)">Subscriptions</button><button class="btn secondary" onclick="adminTab('system',this)">System</button></div><div id="adminContent"><div class="card empty">Loading admin dashboard…</div></div></div></main></div><div id="adminUserModal" class="modal-backdrop hidden"><div class="modal" style="width:min(900px,100%)"><div id="adminUserDetail"></div><div class="actions"><button class="btn secondary" onclick="closeModal('adminUserModal')">Close</button></div></div></div>
<div id="nodeModal" class="modal-backdrop hidden"><div class="modal"><h3>Manage Windows Node</h3><div class="field"><label>Computer name</label><input id="manageNodeName" class="input"></div><div class="field"><label>Permission level</label><select id="managePermission"><option value="read">read</option><option value="operate">operate</option><option value="admin">admin</option></select></div><div class="field"><label>Allowed folders (one path per line)</label><textarea id="manageRoots" class="input" style="min-height:120px"></textarea></div><div class="field"><label>Node log</label><pre id="manageLogs" class="details card" style="max-height:220px;overflow:auto">Load logs after the node is online.</pre></div><div class="actions"><button class="btn danger" onclick="unpairNode()">Unpair</button><button class="btn secondary" onclick="loadNodeLogs()">Refresh logs</button><button class="btn secondary" onclick="closeModal('nodeModal')">Close</button><button class="btn primary" onclick="saveNodeConfig()">Save</button></div></div></div>
<div id="aiModal" class="modal-backdrop hidden"><div class="modal"><h3>Add AI connection</h3><p class="muted">Lucas accepts multiple independent OAuth-capable MCP clients. Choose a client for setup guidance, then add the same MCP URL in that client.</p><div class="field"><label>AI / MCP client</label><select id="aiClientType" onchange="updateAiHelp()"><option>ChatGPT</option><option>Claude</option><option>Gemini</option><option>Cursor</option><option>Codex</option><option>Claude Code</option><option>Other MCP client</option></select></div><div class="field"><label>MCP Server URL</label><input id="aiModalUrl" class="input" readonly value="https://lucas.autozon.xyz/mcp"></div><div id="aiHelp" class="card muted"></div><div class="actions"><button class="btn secondary" onclick="closeModal('aiModal')">Close</button><button class="btn primary" onclick="copyMcpUrl()">Copy MCP URL</button></div></div></div><div id="pairModal" class="modal-backdrop hidden"><div class="modal"><h3>Pair Windows Computer</h3><p class="muted">Download and run the Lucas Node script on the Windows PC, then enter the one-time code generated here. Lucas will identify the computer automatically and save a persistent token after the first successful connection.</p><div class="field"><label>Computer name (optional)</label><input id="pairNodeName" class="input" placeholder="Office PC"></div><p><a class="btn secondary" style="text-decoration:none" href="/download/Lucas-Node.bat">Download Lucas Node</a></p><div id="pairResult" class="card hidden"><div class="muted">Lucas pairing code</div><div id="pairCode" class="metric"></div><div class="path" id="pairCommand"></div></div><div class="actions"><button class="btn secondary" onclick="closeModal('pairModal')">Close</button><button class="btn primary" onclick="createPairCode()">Generate code</button></div></div></div>
<div id="toast" class="toast hidden"></div>
<script>
const state={user:null,nodes:[],aiClients:[]};
async function api(url,opt={}){const r=await fetch(url,{credentials:'include',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});let d={};try{d=await r.json()}catch{}if(r.status===401){showAuth();throw new Error('Please sign in')}if(!r.ok)throw new Error(d.error||('Request failed: '+r.status));return d}
function toast(t){const e=document.getElementById('toast');e.textContent=t;e.classList.remove('hidden');setTimeout(()=>e.classList.add('hidden'),2600)}
function showAuth(){document.getElementById('app').classList.add('hidden');document.getElementById('auth').classList.remove('hidden')}
function showApp(){document.getElementById('auth').classList.add('hidden');document.getElementById('app').classList.remove('hidden')}
function authError(t){const e=document.getElementById('authError');e.textContent=t;e.classList.toggle('hidden',!t)}
function showRegister(v){authError('');document.getElementById('loginForm').classList.toggle('hidden',v);document.getElementById('registerForm').classList.toggle('hidden',!v)}
async function login(){try{await api('/auth/login',{method:'POST',body:JSON.stringify({email:loginEmail.value,password:loginPassword.value})});await boot()}catch(e){authError(e.message)}}
async function registerUser(){try{await api('/auth/register',{method:'POST',body:JSON.stringify({name:regName.value,email:regEmail.value,password:regPassword.value})});await boot()}catch(e){authError(e.message)}}
async function logout(){await api('/api/logout',{method:'POST'}).catch(()=>{});showAuth()}
function view(id,el){document.querySelectorAll('.view').forEach(x=>x.classList.add('hidden'));document.getElementById(id).classList.remove('hidden');document.querySelectorAll('.nav').forEach(x=>x.classList.remove('active'));if(el)el.classList.add('active');if(id==='logs')loadLogs();if(id==='admin')adminTab('dashboard',document.querySelector('#adminTabs button'))}
function closeModal(id){document.getElementById(id).classList.add('hidden')}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function timefmt(v){return v?new Date(v*1000).toLocaleString():'—'}
async function boot(){try{const me=await api('/auth/me');state.user=me.user;showApp();userName.textContent=state.user.name||state.user.email;userEmail.textContent=state.user.email;accountName.textContent=state.user.name||'Account';accountEmail.textContent=state.user.email;accountProvider.textContent=state.user.provider;if(['admin','super_admin'].includes(state.user.role))adminNav.classList.remove('hidden');await refresh()}catch(e){showAuth()}}
async function refresh(){const [n,l,a]=await Promise.all([api('/api/nodes'),api('/api/logs?limit=20'),api('/api/ai-connections')]);state.nodes=n.nodes;state.aiClients=a.clients||[];renderNodes();renderRecent(l.logs);renderAiClients();metricPairedNodes.textContent=state.nodes.length;metricNodes.textContent=state.nodes.filter(x=>x.online).length;metricAiClients.textContent=state.aiClients.length}
function renderNodes(){if(!state.nodes.length){nodeTable.innerHTML='<div class="card empty">No paired computers yet.</div>';return}nodeTable.innerHTML='<table class="table"><thead><tr><th>Computer</th><th>Status</th><th>Permission</th><th>Allowed folders</th><th>Last seen</th><th></th></tr></thead><tbody>'+state.nodes.map(n=>`<tr><td><b>${esc(n.name||n.node_id)}</b><div class="muted">${esc(n.node_id)}</div></td><td><span class="badge ${n.online?'online':'offline'}">${n.online?'Online':'Offline'}</span></td><td>${esc(n.permission_level||'operate')}</td><td class="path">${esc((n.allowed_roots||[]).join('\n')||'—')}</td><td>${esc(timefmt(n.last_seen||n.updated_at))}</td><td><button class="btn secondary" onclick="openNodeModal('${encodeURIComponent(n.node_id)}')">Manage</button></td></tr>`).join('')+'</tbody></table>'}
function renderRecent(logs){recentLogs.innerHTML=logs.length?'<table class="table"><tbody>'+logs.slice(0,8).map(l=>`<tr><td>${esc(timefmt(l.created_at))}</td><td><b>${esc(l.action)}</b><div class="muted">${esc(l.target||'')}</div></td></tr>`).join('')+'</tbody></table>':'<div class="empty">No activity yet.</div>'}
async function loadLogs(){const q=new URLSearchParams({limit:'200'});if(logAction.value)q.set('action',logAction.value);if(logTarget.value)q.set('target',logTarget.value);const d=await api('/api/logs?'+q);logTable.innerHTML=d.logs.length?'<table class="table"><thead><tr><th>Time</th><th>Action</th><th>Target</th><th>Details</th></tr></thead><tbody>'+d.logs.map(l=>`<tr><td>${esc(timefmt(l.created_at))}</td><td>${esc(l.action)}</td><td>${esc(l.target||'')}</td><td><pre class="details">${esc(JSON.stringify(l.details||{},null,2))}</pre></td></tr>`).join('')+'</tbody></table>':'<div class="card empty">No matching activity.</div>'}
function renderAiClients(){if(!state.aiClients.length){aiClientTable.innerHTML='<div class="empty">No OAuth clients registered yet.</div>';return}aiClientTable.innerHTML='<table class="table"><thead><tr><th>Client</th><th>Registered</th></tr></thead><tbody>'+state.aiClients.map(c=>`<tr><td><b>${esc(c.client_name||'MCP Client')}</b></td><td>${esc(timefmt(c.created_at))}</td></tr>`).join('')+'</tbody></table>'}
let managedNodeId=null;
function openNodeModal(id){managedNodeId=decodeURIComponent(id);const n=state.nodes.find(x=>x.node_id===managedNodeId);if(!n)return;manageNodeName.value=n.name||n.node_id;managePermission.value=n.permission_level||'operate';manageRoots.value=(n.allowed_roots||[]).join('\n');manageLogs.textContent='Click Refresh logs to load the latest local Lucas Node log.';nodeModal.classList.remove('hidden')}
async function saveNodeConfig(){if(!managedNodeId)return;const roots=manageRoots.value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);try{await api('/api/nodes/'+encodeURIComponent(managedNodeId)+'/config',{method:'PUT',body:JSON.stringify({name:manageNodeName.value.trim(),permission_level:managePermission.value,allowed_roots:roots})});toast('Node settings saved');await refresh()}catch(e){toast(e.message)}}
async function loadNodeLogs(){if(!managedNodeId)return;try{const d=await api('/api/nodes/'+encodeURIComponent(managedNodeId)+'/logs?limit=250');manageLogs.textContent=(d.lines||[]).join('\n')||'No log lines yet.'}catch(e){manageLogs.textContent=e.message}}
async function unpairNode(){if(!managedNodeId||!confirm('Unpair this Windows computer? It will need a new pairing code to reconnect.'))return;await api('/api/nodes/'+encodeURIComponent(managedNodeId),{method:'DELETE'});closeModal('nodeModal');toast('Windows node unpaired');await refresh()}
async function copyMcpUrl(){const u=location.origin+'/mcp';mcpUrl.value=u;try{await navigator.clipboard.writeText(u);toast('MCP URL copied')}catch{mcpUrl.select();document.execCommand('copy');toast('MCP URL copied')}}
function openAiModal(){aiModal.classList.remove('hidden');aiModalUrl.value=location.origin+'/mcp';updateAiHelp()}
function updateAiHelp(){const n=aiClientType.value;const tips={ChatGPT:'Create a custom MCP app, use the Lucas MCP URL, choose OAuth, then scan tools.',Claude:'Add Lucas as a remote MCP connector and use OAuth when prompted.',Gemini:'Add Lucas through an MCP-compatible integration and authorize with Lucas OAuth.',Cursor:'Add a remote MCP server using the Lucas MCP URL and complete OAuth authorization.',Codex:'Configure Lucas as a remote MCP server using the URL shown above.','Claude Code':'Configure Lucas as a remote MCP server using the URL shown above.','Other MCP client':'Use Streamable HTTP with the Lucas MCP URL. OAuth metadata and dynamic client registration are published automatically.'};aiHelp.textContent=tips[n]||tips['Other MCP client']}
function openPairModal(){pairNodeName.value='';pairResult.classList.add('hidden');pairModal.classList.remove('hidden')}
async function createPairCode(){const name=pairNodeName.value.trim()||'Windows PC';const d=await api('/api/nodes/pair',{method:'POST',body:JSON.stringify({name})});pairCode.textContent=d.pairing_code;pairCommand.textContent=`Run the downloaded Lucas Node script on the Windows PC and enter pairing code ${d.pairing_code}. Lucas will identify this computer automatically.`;pairResult.classList.remove('hidden')}
function adminMetric(label,value){return `<div class="card"><div class="muted">${esc(label)}</div><div class="metric">${esc(value)}</div></div>`}
async function adminTab(tab,el){document.querySelectorAll('#adminTabs button').forEach(b=>{b.classList.remove('primary');b.classList.add('secondary')});if(el){el.classList.remove('secondary');el.classList.add('primary')}adminContent.innerHTML='<div class="card empty">Loading…</div>';try{if(tab==='dashboard'){const d=await api('/api/admin/dashboard');adminContent.innerHTML=`<div class="grid">${adminMetric('Total users',d.users)}${adminMetric('Active users · 7d',d.active_users_7d)}${adminMetric('Online nodes',d.online_nodes)}${adminMetric('Operations today',d.operations_today)}${adminMetric('Operations · 30d',d.operations_30d)}${adminMetric('Paid users',d.paid_users)}</div><div class="card" style="margin-top:16px"><h3>Recent activity</h3>${d.recent.length?'<table class="table"><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Target</th></tr></thead><tbody>'+d.recent.map(r=>`<tr><td>${esc(timefmt(r.created_at))}</td><td>${esc(r.email||'—')}</td><td>${esc(r.action)}</td><td>${esc(r.target||'—')}</td></tr>`).join('')+'</tbody></table>':'<div class="empty">No activity.</div>'}</div>`}else if(tab==='users'){const d=await api('/api/admin/users');adminContent.innerHTML=`<div class="toolbar"><input id="adminUserSearch" class="input" placeholder="Search email or name"><button class="btn secondary" onclick="adminSearchUsers()">Search</button></div><div id="adminUsersTable">${renderAdminUsers(d.users)}</div>`}else if(tab==='usage'){const d=await api('/api/admin/usage');adminContent.innerHTML=`<div class="grid">${adminMetric('Requests · 30d',d.requests_30d)}${adminMetric('Operations · 30d',d.operations_30d)}${adminMetric('Execution · 30d',Math.round(d.execution_seconds_30d)+'s')}${adminMetric('Success rate',d.success_rate+'%')}${adminMetric('Failed · 30d',d.errors_30d)}${adminMetric('Files / Shell / Git',(d.by_tool.files||0)+' / '+(d.by_tool.shell||0)+' / '+(d.by_tool.git||0))}</div><div class="card" style="margin-top:16px"><h3>Top users · 30d</h3><table class="table"><thead><tr><th>User</th><th>Operations</th></tr></thead><tbody>${d.top_users.map(r=>`<tr><td>${esc(r.email)}</td><td>${esc(r.n)}</td></tr>`).join('')}</tbody></table></div>`}else if(tab==='nodes'){const d=await api('/api/admin/nodes');adminContent.innerHTML=d.nodes.length?`<table class="table"><thead><tr><th>Node</th><th>Owner</th><th>Platform</th><th>Status</th><th>Allowed folders</th><th>Last seen</th></tr></thead><tbody>${d.nodes.map(n=>`<tr><td><b>${esc(n.name)}</b><div class="muted">${esc(n.node_id)}</div></td><td>${esc(n.owner||'—')}</td><td>${esc(n.platform)}</td><td><span class="badge ${n.online?'online':'offline'}">${n.online?'Online':'Offline'}</span></td><td>${esc(n.allowed_folder_count)}</td><td>${esc(timefmt(n.updated_at))}</td></tr>`).join('')}</tbody></table>`:'<div class="card empty">No nodes.</div>'}else if(tab==='operations'){const d=await api('/api/admin/operations?limit=300');adminContent.innerHTML=`<div class="toolbar"><input id="adminOpUser" class="input" placeholder="User"><input id="adminOpAction" class="input" placeholder="Tool / action"><button class="btn secondary" onclick="adminFilterOps()">Filter</button></div><div id="adminOpsTable">${renderAdminOps(d.operations)}</div>`}else if(tab==='subscriptions'){const d=await api('/api/admin/subscriptions');adminContent.innerHTML=`<table class="table"><thead><tr><th>User</th><th>Plan</th><th>Status</th><th>Provider</th><th>Ends</th></tr></thead><tbody>${d.subscriptions.map(s=>`<tr><td>${esc(s.email)}</td><td>${esc(s.plan)}</td><td>${esc(s.status)}</td><td>${esc(s.billing_provider||'—')}</td><td>${esc(timefmt(s.ends_at))}</td></tr>`).join('')}</tbody></table>`}else if(tab==='system'){const d=await api('/api/admin/system');adminContent.innerHTML=`<div class="grid">${adminMetric('Gateway',d.gateway)}${adminMetric('Database',d.database)}${adminMetric('Online nodes',d.online_nodes)}${adminMetric('Total nodes',d.total_nodes)}${adminMetric('Users',d.users)}${adminMetric('Server time',new Date(d.server_time*1000).toLocaleString())}</div>`}}catch(e){adminContent.innerHTML=`<div class="error">${esc(e.message)}</div>`}}
function renderAdminUsers(rows){return rows.length?'<table class="table"><thead><tr><th>User</th><th>Role</th><th>Status</th><th>Plan</th><th>Nodes</th><th>Ops 30d</th><th>Last active</th></tr></thead><tbody>'+rows.map(u=>`<tr style="cursor:pointer" onclick="showAdminUser('${u.id}')"><td><b>${esc(u.email)}</b><div class="muted">${esc(u.name||'')}</div></td><td>${esc(u.role)}</td><td>${esc(u.status)}</td><td>${esc(u.plan)}</td><td>${esc(u.node_count)}</td><td>${esc(u.operations_30d)}</td><td>${esc(timefmt(u.last_login_at))}</td></tr>`).join('')+'</tbody></table>':'<div class="card empty">No users.</div>'}
async function adminSearchUsers(){const d=await api('/api/admin/users?q='+encodeURIComponent(adminUserSearch.value));adminUsersTable.innerHTML=renderAdminUsers(d.users)}
function renderAdminOps(rows){return rows.length?'<table class="table"><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Target</th><th>Status</th></tr></thead><tbody>'+rows.map(o=>`<tr><td>${esc(timefmt(o.created_at))}</td><td>${esc(o.email||'—')}</td><td>${esc(o.action)}</td><td>${esc(o.target||'—')}</td><td>${esc(o.status)}</td></tr>`).join('')+'</tbody></table>':'<div class="card empty">No operations.</div>'}
async function adminFilterOps(){const q=new URLSearchParams({limit:'300'});if(adminOpUser.value)q.set('user',adminOpUser.value);if(adminOpAction.value)q.set('action',adminOpAction.value);const d=await api('/api/admin/operations?'+q);adminOpsTable.innerHTML=renderAdminOps(d.operations)}
async function saveAdminUser(id){await api('/api/admin/users/'+encodeURIComponent(id),{method:'PUT',body:JSON.stringify({status:adminDetailStatus.value,plan:adminDetailPlan.value})});toast('User updated');await showAdminUser(id)}
async function showAdminUser(id){const d=await api('/api/admin/users/'+encodeURIComponent(id));const u=d.user;adminUserDetail.innerHTML=`<h3>${esc(u.email)}</h3><div class="grid">${adminMetric('Plan',d.subscription.plan)}${adminMetric('Nodes',d.nodes.length)}${adminMetric('Operations · 30d',d.usage.last30||0)}</div><div class="card" style="margin-top:14px"><div class="row"><div><b>Role</b><div>${esc(u.role)}</div></div><div><b>Status</b><select id="adminDetailStatus"><option value="active" ${u.status==='active'?'selected':''}>active</option><option value="disabled" ${u.status==='disabled'?'selected':''}>disabled</option></select></div><div><b>Plan</b><select id="adminDetailPlan"><option value="free" ${d.subscription.plan==='free'?'selected':''}>free</option><option value="pro" ${d.subscription.plan==='pro'?'selected':''}>pro</option><option value="team" ${d.subscription.plan==='team'?'selected':''}>team</option><option value="enterprise" ${d.subscription.plan==='enterprise'?'selected':''}>enterprise</option></select></div></div><div class="actions"><button class="btn primary" onclick="saveAdminUser('${u.id}')">Save account</button></div></div><h3 style="margin-top:18px">Nodes</h3>${d.nodes.length?'<table class="table"><tbody>'+d.nodes.map(n=>`<tr><td>${esc(n.name)}</td><td>${esc(n.permission_level)}</td><td>${esc(timefmt(n.updated_at))}</td></tr>`).join('')+'</tbody></table>':'<div class="empty">No nodes.</div>'}<h3 style="margin-top:18px">Recent operations</h3>${renderAdminOps(d.operations.map(o=>({...o,email:u.email,status:(o.details||{}).status||'success'})))}`;adminUserModal.classList.remove('hidden')}
boot();
</script>
</body></html>'''


def _auth_user(request: Request):
    token = ""
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        token = request.cookies.get("gwc_access_token", "")
    return gateway.auth.verify_token(token)


def _safe_details(raw: str | None) -> dict:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    blocked = {"password", "token", "access_token", "authorization", "cookie", "clipboard", "content"}
    return {k: ("[redacted]" if k.lower() in blocked else v) for k, v in data.items()}


def _db() -> sqlite3.Connection:
    db = sqlite3.connect(gateway.db_path, timeout=30)
    db.row_factory = sqlite3.Row
    return db


async def home(_: Request):
    return HTMLResponse(DASHBOARD_HTML)


async def download_lucas_node(_: Request):
    return FileResponse(
        "/app/scripts/install-node.ps1",
        media_type="application/octet-stream",
        filename="Lucas-Node.ps1",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


async def download_lucas_launcher(_: Request):
    return FileResponse(
        "/app/scripts/Lucas-Node.bat",
        media_type="application/octet-stream",
        filename="Lucas-Node.bat",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


async def api_logout(_: Request):
    response = JSONResponse({"ok": True})
    response.delete_cookie("gwc_access_token")
    return response


async def api_nodes(request: Request):
    user = _auth_user(request)
    online = {n["node_id"]: n for n in gateway.registry.list(user.id)}
    with _db() as db:
        rows = db.execute("SELECT node_id,name,updated_at,permission_level,allowed_roots FROM nodes WHERE owner_user_id=? ORDER BY name", (user.id,)).fetchall()
    result = []
    for row in rows:
        live = online.pop(row["node_id"], None)
        if live:
            result.append(live)
        else:
            try:
                roots = json.loads(row["allowed_roots"] or "[]")
            except json.JSONDecodeError:
                roots = []
            result.append({"node_id": row["node_id"], "name": row["name"], "online": False, "updated_at": row["updated_at"], "permission_level": row["permission_level"] or "operate", "allowed_roots": roots})
    result.extend(online.values())
    return JSONResponse({"nodes": result})


async def api_pair_node(request: Request):
    user = _auth_user(request)
    body = await request.json()
    node_id = str(body.get("node_id", "")).strip()
    name = str(body.get("name") or node_id or "Windows PC").strip()
    ttl = max(60, min(int(body.get("ttl_seconds", 600)), 3600))
    code = f"{secrets.randbelow(1_000_000):06d}"
    gateway._pairings[code] = {"node_id": node_id or None, "name": name, "owner_user_id": user.id, "expires": time.time() + ttl}
    gateway.auth.audit(user.id, "node.pair_code", node_id or "pending")
    return JSONResponse({"node_id": node_id or None, "name": name, "pairing_code": code, "expires_in": ttl})


async def api_node_config(request: Request):
    user = _auth_user(request)
    node_id = unquote(request.path_params["node_id"])
    record = await gateway.auth_store.record_for(node_id)
    if not record or record.get("owner_user_id") != user.id:
        return JSONResponse({"error": "Node not found"}, status_code=404)
    if request.method == "GET":
        try:
            roots = json.loads(record.get("allowed_roots") or "[]")
        except json.JSONDecodeError:
            roots = []
        return JSONResponse({"node_id": node_id, "name": record.get("name"), "permission_level": record.get("permission_level") or "operate", "allowed_roots": roots})
    body = await request.json()
    name = str(body.get("name") or record.get("name") or node_id).strip()
    permission = str(body.get("permission_level") or "operate").strip().lower()
    roots = [str(item).strip() for item in (body.get("allowed_roots") or []) if str(item).strip()]
    if permission not in {"read", "operate", "admin"}:
        return JSONResponse({"error": "Invalid permission level"}, status_code=400)
    if not roots:
        return JSONResponse({"error": "At least one allowed folder is required"}, status_code=400)
    try:
        if node_id in gateway.registry.nodes:
            await gateway.registry.rpc(node_id, user.id, "node.configure", {"node_name": name, "permission_level": permission, "allowed_roots": roots}, timeout=30)
        updated = await gateway.auth_store.update_config(node_id, user.id, name, permission, roots)
        live = gateway.registry.nodes.get(node_id)
        if live:
            live.name = name
            live.permission_level = permission
            live.allowed_roots = roots
        gateway.auth.audit(user.id, "node.configure", node_id, {"permission_level": permission, "allowed_roots": roots})
        return JSONResponse({"ok": True, "node_id": node_id})
    except (RuntimeError, PermissionError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_node_logs(request: Request):
    user = _auth_user(request)
    node_id = unquote(request.path_params["node_id"])
    try:
        gateway.registry.require_owned(node_id, user.id)
        limit = max(20, min(int(request.query_params.get("limit", "250")), 1000))
        result = await gateway.registry.rpc(node_id, user.id, "node.logs", {"limit": limit}, timeout=30)
        return JSONResponse(result)
    except (RuntimeError, PermissionError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_node_delete(request: Request):
    user = _auth_user(request)
    node_id = unquote(request.path_params["node_id"])
    removed = await gateway.auth_store.delete(node_id, user.id)
    connection = gateway.registry.nodes.get(node_id)
    if connection and connection.owner_user_id == user.id:
        await connection.websocket.close(code=4002)
    gateway.auth.audit(user.id, "node.unpair", node_id)
    return JSONResponse({"removed": removed})


async def api_folders(request: Request):
    user = _auth_user(request)
    node_id = unquote(request.path_params["node_id"])
    path = request.query_params.get("path")
    try:
        gateway.registry.require_owned(node_id, user.id)
        result = await gateway.registry.rpc(node_id, user.id, "workspace.browse", {"path": path} if path else {})
        return JSONResponse(result)
    except (RuntimeError, PermissionError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_ai_connections(request: Request):
    user = _auth_user(request)
    with _db() as db:
        rows = db.execute("SELECT client_id,client_name,created_at FROM oauth_clients ORDER BY created_at DESC").fetchall()
    return JSONResponse({"clients": [{"client_id": r["client_id"], "client_name": r["client_name"], "created_at": r["created_at"]} for r in rows]})


async def api_logs(request: Request):
    user = _auth_user(request)
    limit = max(1, min(int(request.query_params.get("limit", "100")), 500))
    action = request.query_params.get("action", "").strip()
    target = request.query_params.get("target", "").strip()
    sql = "SELECT id,action,target,details,created_at FROM audit_logs WHERE user_id=?"
    params: list[object] = [user.id]
    if action:
        sql += " AND action LIKE ?"
        params.append(f"%{action}%")
    if target:
        sql += " AND target LIKE ?"
        params.append(f"%{target}%")
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with _db() as db:
        rows = db.execute(sql, params).fetchall()
    logs = [{"id": r["id"], "action": r["action"], "target": r["target"], "details": _safe_details(r["details"]), "created_at": r["created_at"]} for r in rows]
    return JSONResponse({"logs": logs})


routes = [
    Route("/", home, methods=["GET"]),
    Route("/download/Lucas-Node.ps1", download_lucas_node, methods=["GET"]),
    Route("/download/Lucas-Node.bat", download_lucas_launcher, methods=["GET"]),
    Route("/api/logout", api_logout, methods=["POST"]),
    Route("/api/nodes", api_nodes, methods=["GET"]),
    Route("/api/nodes/pair", api_pair_node, methods=["POST"]),
    Route("/api/nodes/{node_id}/config", api_node_config, methods=["GET", "PUT"]),
    Route("/api/nodes/{node_id}/logs", api_node_logs, methods=["GET"]),
    Route("/api/nodes/{node_id}", api_node_delete, methods=["DELETE"]),
    Route("/api/nodes/{node_id}/folders", api_folders, methods=["GET"]),
    Route("/api/ai-connections", api_ai_connections, methods=["GET"]),
    Route("/api/logs", api_logs, methods=["GET"]),
    *admin_routes,
    Mount("/", app=gateway.app),
]

app = Starlette(routes=routes)


def main() -> None:
    uvicorn.run(app, host=gateway.settings.host, port=gateway.settings.port, log_level="info")


if __name__ == "__main__":
    main()
