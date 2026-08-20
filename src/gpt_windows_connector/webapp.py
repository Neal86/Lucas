from __future__ import annotations

import json
import secrets
import sqlite3
import time
from urllib.parse import unquote

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Mount, Route

from . import gateway


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
<div id="auth" class="auth hidden"><div class="auth-card"><div class="brand">Lucas</div><div class="sub">Connect your AI projects to your Windows computers through your VPS.</div><div id="authError" class="error hidden"></div><div id="loginForm"><div class="field"><label>Email</label><input id="loginEmail" class="input" type="email" autocomplete="email"></div><div class="field"><label>Password</label><input id="loginPassword" class="input" type="password" autocomplete="current-password"></div><button class="btn primary" style="width:100%" onclick="login()">Sign in</button><button class="btn google" onclick="location.href='/auth/google/start'">Continue with Google</button><p class="muted" style="margin:16px 0 0">No account? <button class="switch" onclick="showRegister(true)">Create one</button></p></div><div id="registerForm" class="hidden"><div class="field"><label>Name</label><input id="regName" class="input"></div><div class="field"><label>Email</label><input id="regEmail" class="input" type="email"></div><div class="field"><label>Password</label><input id="regPassword" class="input" type="password" placeholder="At least 10 characters"></div><button class="btn primary" style="width:100%" onclick="registerUser()">Create account</button><button class="btn google" onclick="location.href='/auth/google/start'">Sign up with Google</button><p class="muted" style="margin:16px 0 0">Already registered? <button class="switch" onclick="showRegister(false)">Sign in</button></p></div></div></div>
<div id="app" class="shell hidden"><aside class="side"><div class="logo">GWC</div><button class="nav active" data-view="dashboard" onclick="view('dashboard',this)">Dashboard</button><button class="nav" data-view="projects" onclick="view('projects',this)">Projects</button><button class="nav" data-view="nodes" onclick="view('nodes',this)">Windows Nodes</button><button class="nav" data-view="logs" onclick="view('logs',this)">Activity Logs</button><button class="nav" data-view="account" onclick="view('account',this)">Account & Security</button><div class="userbox"><div id="userName"></div><small id="userEmail"></small><div style="margin-top:10px"><button class="btn secondary" onclick="logout()">Sign out</button></div></div></aside><main class="main"><div id="dashboard" class="view"><div class="top"><div><h2>Dashboard</h2><p class="muted">Your projects, computers, and recent activity.</p></div><button class="btn primary" onclick="openProjectModal()">New project</button></div><div class="grid"><div class="card"><div class="muted">Projects</div><div id="metricProjects" class="metric">0</div></div><div class="card"><div class="muted">Online Windows nodes</div><div id="metricNodes" class="metric">0</div></div><div class="card"><div class="muted">Recent actions</div><div id="metricLogs" class="metric">0</div></div></div><div class="card" style="margin-top:16px"><h3>Recent activity</h3><div id="recentLogs"></div></div></div><div id="projects" class="view hidden"><div class="top"><div><h2>Projects</h2><p class="muted">Each project is bound to one Windows node and one allowed folder.</p></div><button class="btn primary" onclick="openProjectModal()">New project</button></div><div id="projectTable"></div></div><div id="nodes" class="view hidden"><div class="top"><div><h2>Windows Nodes</h2><p class="muted">Download the Lucas pairing script, generate a code, and connect this Windows PC.</p></div><div style="display:flex;gap:8px"><a class="btn secondary" style="text-decoration:none" href="https://github.com/Neal86/Lucas/raw/refs/heads/main/scripts/install-node.ps1">Download Lucas Node</a><button class="btn primary" onclick="openPairModal()">Pair computer</button></div></div><div id="nodeTable"></div></div><div id="logs" class="view hidden"><div class="top"><div><h2>Activity Logs</h2><p class="muted">Only activity belonging to your account is shown.</p></div></div><div class="log-filter"><input id="logAction" class="input" placeholder="Action filter"><input id="logTarget" class="input" placeholder="Project / target"><button class="btn secondary" onclick="loadLogs()">Filter</button></div><div id="logTable"></div></div><div id="account" class="view hidden"><div class="top"><div><h2>Account & Security</h2><p class="muted">Authentication and connector security information.</p></div></div><div class="card"><h3 id="accountName"></h3><p id="accountEmail"></p><p class="muted">Authentication provider: <span id="accountProvider"></span></p><p class="muted">All AI-to-Windows traffic is relayed through this VPS Gateway. Windows nodes do not require a public inbound port.</p></div></div></main></div>
<div id="projectModal" class="modal-backdrop hidden"><div class="modal"><h3>Bind Project</h3><div class="field"><label>Project name / ID</label><input id="projectId" class="input" placeholder="NiceC-WMS"></div><div class="field"><label>Windows computer</label><select id="projectNode" onchange="browseFolders(null)"></select></div><div class="field"><label>Workspace folder</label><div id="selectedPath" class="path">Select a folder below</div><div class="folderbox" id="folderBox"></div></div><div class="actions"><button class="btn secondary" onclick="closeModal('projectModal')">Cancel</button><button class="btn primary" onclick="saveProject()">Bind project</button></div></div></div>
<div id="pairModal" class="modal-backdrop hidden"><div class="modal"><h3>Pair Windows Computer</h3><p class="muted">Create a one-time code, then start the Windows Node using this code. The node will save a persistent token after the first successful connection.</p><div class="row"><div class="field"><label>Node ID</label><input id="pairNodeId" class="input" placeholder="Office-PC"></div><div class="field"><label>Name</label><input id="pairNodeName" class="input" placeholder="Office PC"></div></div><div id="pairResult" class="card hidden"><div class="muted">Pairing code</div><div id="pairCode" class="metric"></div><div class="path" id="pairCommand"></div></div><div class="actions"><button class="btn secondary" onclick="closeModal('pairModal')">Close</button><button class="btn primary" onclick="createPairCode()">Generate code</button></div></div></div>
<div id="toast" class="toast hidden"></div>
<script>
const state={user:null,projects:[],nodes:[],selectedPath:null};
async function api(url,opt={}){const r=await fetch(url,{credentials:'include',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});let d={};try{d=await r.json()}catch{}if(r.status===401){showAuth();throw new Error('Please sign in')}if(!r.ok)throw new Error(d.error||('Request failed: '+r.status));return d}
function toast(t){const e=document.getElementById('toast');e.textContent=t;e.classList.remove('hidden');setTimeout(()=>e.classList.add('hidden'),2600)}
function showAuth(){document.getElementById('app').classList.add('hidden');document.getElementById('auth').classList.remove('hidden')}
function showApp(){document.getElementById('auth').classList.add('hidden');document.getElementById('app').classList.remove('hidden')}
function authError(t){const e=document.getElementById('authError');e.textContent=t;e.classList.toggle('hidden',!t)}
function showRegister(v){authError('');document.getElementById('loginForm').classList.toggle('hidden',v);document.getElementById('registerForm').classList.toggle('hidden',!v)}
async function login(){try{await api('/auth/login',{method:'POST',body:JSON.stringify({email:loginEmail.value,password:loginPassword.value})});await boot()}catch(e){authError(e.message)}}
async function registerUser(){try{await api('/auth/register',{method:'POST',body:JSON.stringify({name:regName.value,email:regEmail.value,password:regPassword.value})});await boot()}catch(e){authError(e.message)}}
async function logout(){await api('/api/logout',{method:'POST'}).catch(()=>{});showAuth()}
function view(id,el){document.querySelectorAll('.view').forEach(x=>x.classList.add('hidden'));document.getElementById(id).classList.remove('hidden');document.querySelectorAll('.nav').forEach(x=>x.classList.remove('active'));if(el)el.classList.add('active');if(id==='logs')loadLogs()}
function closeModal(id){document.getElementById(id).classList.add('hidden')}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function timefmt(v){return v?new Date(v*1000).toLocaleString():'—'}
async function boot(){try{const me=await api('/auth/me');state.user=me.user;showApp();userName.textContent=state.user.name||state.user.email;userEmail.textContent=state.user.email;accountName.textContent=state.user.name||'Account';accountEmail.textContent=state.user.email;accountProvider.textContent=state.user.provider;await refresh()}catch(e){showAuth()}}
async function refresh(){const [p,n,l]=await Promise.all([api('/api/projects'),api('/api/nodes'),api('/api/logs?limit=20')]);state.projects=p.projects;state.nodes=n.nodes;renderProjects();renderNodes();renderRecent(l.logs);metricProjects.textContent=state.projects.length;metricNodes.textContent=state.nodes.filter(x=>x.online).length;metricLogs.textContent=l.logs.length}
function renderProjects(){if(!state.projects.length){projectTable.innerHTML='<div class="card empty">No projects bound yet.</div>';return}projectTable.innerHTML='<table class="table"><thead><tr><th>Project</th><th>Computer</th><th>Workspace</th><th></th></tr></thead><tbody>'+state.projects.map(p=>`<tr><td><b>${esc(p.name||p.project_id)}</b><div class="muted">${esc(p.project_id)}</div></td><td>${esc(p.node_id)}</td><td class="path">${esc(p.workspace)}</td><td><button class="btn danger" onclick="removeProject('${encodeURIComponent(p.project_id)}')">Unbind</button></td></tr>`).join('')+'</tbody></table>'}
function renderNodes(){if(!state.nodes.length){nodeTable.innerHTML='<div class="card empty">No paired computers yet.</div>';return}nodeTable.innerHTML='<table class="table"><thead><tr><th>Computer</th><th>Status</th><th>Permission</th><th>Last seen</th></tr></thead><tbody>'+state.nodes.map(n=>`<tr><td><b>${esc(n.name||n.node_id)}</b><div class="muted">${esc(n.node_id)}</div></td><td><span class="badge ${n.online?'online':'offline'}">${n.online?'Online':'Offline'}</span></td><td>${esc(n.permission_level||'—')}</td><td>${esc(timefmt(n.last_seen||n.updated_at))}</td></tr>`).join('')+'</tbody></table>'}
function renderRecent(logs){recentLogs.innerHTML=logs.length?'<table class="table"><tbody>'+logs.slice(0,8).map(l=>`<tr><td>${esc(timefmt(l.created_at))}</td><td><b>${esc(l.action)}</b><div class="muted">${esc(l.target||'')}</div></td></tr>`).join('')+'</tbody></table>':'<div class="empty">No activity yet.</div>'}
async function loadLogs(){const q=new URLSearchParams({limit:'200'});if(logAction.value)q.set('action',logAction.value);if(logTarget.value)q.set('target',logTarget.value);const d=await api('/api/logs?'+q);logTable.innerHTML=d.logs.length?'<table class="table"><thead><tr><th>Time</th><th>Action</th><th>Target</th><th>Details</th></tr></thead><tbody>'+d.logs.map(l=>`<tr><td>${esc(timefmt(l.created_at))}</td><td>${esc(l.action)}</td><td>${esc(l.target||'')}</td><td><pre class="details">${esc(JSON.stringify(l.details||{},null,2))}</pre></td></tr>`).join('')+'</tbody></table>':'<div class="card empty">No matching activity.</div>'}
async function removeProject(id){if(!confirm('Unbind this project?'))return;await api('/api/projects/'+id,{method:'DELETE'});toast('Project unbound');await refresh()}
function openProjectModal(){if(!state.nodes.some(n=>n.online)){toast('Pair and connect a Windows computer first');return}projectId.value='';state.selectedPath=null;selectedPath.textContent='Select a folder below';projectNode.innerHTML=state.nodes.filter(n=>n.online).map(n=>`<option value="${esc(n.node_id)}">${esc(n.name||n.node_id)} (${esc(n.node_id)})</option>`).join('');projectModal.classList.remove('hidden');browseFolders(null)}
async function browseFolders(path){const node=projectNode.value;if(!node)return;folderBox.innerHTML='<div class="empty">Loading folders…</div>';const q=path?('?path='+encodeURIComponent(path)):'';try{const d=await api('/api/nodes/'+encodeURIComponent(node)+'/folders'+q);let rows=[];if(d.parent)rows.push(`<div class="folder" onclick='browseFolders(${JSON.stringify(d.parent)})'>⬆ <div><b>Parent folder</b><div class="path">${esc(d.parent)}</div></div></div>`);for(const r of (d.roots||[]))rows.push(`<div class="folder" onclick='selectAndBrowse(${JSON.stringify(r.path)})'>💽 <div><b>${esc(r.name)}</b><div class="path">${esc(r.path)}</div></div></div>`);for(const r of (d.directories||[]))rows.push(`<div class="folder" onclick='selectAndBrowse(${JSON.stringify(r.path)})'>📁 <div><b>${esc(r.name)}</b><div class="path">${esc(r.path)}</div></div></div>`);folderBox.innerHTML=rows.join('')||'<div class="empty">No subfolders.</div>';if(d.path){state.selectedPath=d.path;selectedPath.textContent=d.path}}catch(e){folderBox.innerHTML='<div class="error">'+esc(e.message)+'</div>'}}
function selectAndBrowse(path){state.selectedPath=path;selectedPath.textContent=path;browseFolders(path)}
async function saveProject(){const id=projectId.value.trim(),node=projectNode.value,path=state.selectedPath;if(!id||!node||!path){toast('Choose a project name, computer, and folder');return}await api('/api/projects',{method:'POST',body:JSON.stringify({project_id:id,name:id,node_id:node,workspace:path})});closeModal('projectModal');toast('Project bound');await refresh()}
function openPairModal(){pairNodeId.value='';pairNodeName.value='';pairResult.classList.add('hidden');pairModal.classList.remove('hidden')}
async function createPairCode(){const id=pairNodeId.value.trim();if(!id){toast('Enter a Node ID');return}const d=await api('/api/nodes/pair',{method:'POST',body:JSON.stringify({node_id:id,name:pairNodeName.value.trim()||id})});pairCode.textContent=d.pairing_code;pairCommand.textContent=`Set GWC_NODE_ID=${id}, GWC_PAIRING_CODE=${d.pairing_code}, and GWC_GATEWAY_WS to your VPS WSS URL, then run gwc-node.`;pairResult.classList.remove('hidden')}
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


async def api_logout(_: Request):
    response = JSONResponse({"ok": True})
    response.delete_cookie("gwc_access_token")
    return response


async def api_projects(request: Request):
    user = _auth_user(request)
    if request.method == "GET":
        return JSONResponse({"projects": [p.__dict__ for p in gateway.bindings.list(user.id)]})
    body = await request.json()
    project_id = str(body.get("project_id", "")).strip()
    node_id = str(body.get("node_id", "")).strip()
    workspace = str(body.get("workspace", "")).strip()
    if not project_id or not node_id or not workspace:
        return JSONResponse({"error": "project_id, node_id and workspace are required"}, status_code=400)
    try:
        gateway.registry.require_owned(node_id, user.id)
        verified = await gateway.registry.rpc(node_id, user.id, "workspace.info", {"workspace": workspace})
        binding = gateway.bindings.set(user.id, project_id, node_id, str(verified["path"]), body.get("name") or project_id)
        gateway.auth.audit(user.id, "project.bind", project_id, {"node_id": node_id, "workspace": binding.workspace})
        return JSONResponse({"project": binding.__dict__}, status_code=201)
    except (RuntimeError, PermissionError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_project_delete(request: Request):
    user = _auth_user(request)
    project_id = unquote(request.path_params["project_id"])
    item = gateway.bindings.get(user.id, project_id)
    if item:
        gateway.registry.release_control(item.node_id, user.id, project_id)
    removed = gateway.bindings.remove(user.id, project_id)
    gateway.auth.audit(user.id, "project.unbind", project_id)
    return JSONResponse({"removed": removed})


async def api_nodes(request: Request):
    user = _auth_user(request)
    online = {n["node_id"]: n for n in gateway.registry.list(user.id)}
    with _db() as db:
        rows = db.execute("SELECT node_id,name,updated_at FROM nodes WHERE owner_user_id=? ORDER BY name", (user.id,)).fetchall()
    result = []
    for row in rows:
        live = online.pop(row["node_id"], None)
        if live:
            result.append(live)
        else:
            result.append({"node_id": row["node_id"], "name": row["name"], "online": False, "updated_at": row["updated_at"], "permission_level": None})
    result.extend(online.values())
    return JSONResponse({"nodes": result})


async def api_pair_node(request: Request):
    user = _auth_user(request)
    body = await request.json()
    node_id = str(body.get("node_id", "")).strip()
    name = str(body.get("name") or node_id).strip()
    if not node_id:
        return JSONResponse({"error": "node_id is required"}, status_code=400)
    ttl = max(60, min(int(body.get("ttl_seconds", 600)), 3600))
    code = f"{secrets.randbelow(1_000_000):06d}"
    gateway._pairings[code] = {"node_id": node_id, "name": name, "owner_user_id": user.id, "expires": time.time() + ttl}
    gateway.auth.audit(user.id, "node.pair_code", node_id)
    return JSONResponse({"node_id": node_id, "name": name, "pairing_code": code, "expires_in": ttl})


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
    Route("/api/logout", api_logout, methods=["POST"]),
    Route("/api/projects", api_projects, methods=["GET", "POST"]),
    Route("/api/projects/{project_id:path}", api_project_delete, methods=["DELETE"]),
    Route("/api/nodes", api_nodes, methods=["GET"]),
    Route("/api/nodes/pair", api_pair_node, methods=["POST"]),
    Route("/api/nodes/{node_id}/folders", api_folders, methods=["GET"]),
    Route("/api/logs", api_logs, methods=["GET"]),
    Mount("/", app=gateway.app),
]

app = Starlette(routes=routes)


def main() -> None:
    uvicorn.run(app, host=gateway.settings.host, port=gateway.settings.port, log_level="info")


if __name__ == "__main__":
    main()
