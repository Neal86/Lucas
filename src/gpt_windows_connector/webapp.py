from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from urllib.parse import unquote

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Mount, Route

from . import gateway
from .admin import admin_routes


BRAND_ASSET_DIR = Path(__file__).with_name("assets")

from .web_assets import DASHBOARD_HTML


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


def _ensure_dashboard_metadata_schema(db: sqlite3.Connection) -> None:
    db.executescript("""
    CREATE TABLE IF NOT EXISTS dashboard_node_metadata(
        user_id TEXT NOT NULL, node_id TEXT NOT NULL, display_name TEXT, updated_at REAL NOT NULL,
        PRIMARY KEY(user_id,node_id)
    );
    CREATE TABLE IF NOT EXISTS dashboard_ai_metadata(
        user_id TEXT NOT NULL, client_id TEXT NOT NULL, display_name TEXT, note TEXT, updated_at REAL NOT NULL,
        PRIMARY KEY(user_id,client_id)
    );
    CREATE TABLE IF NOT EXISTS dashboard_pending_node_access(
        user_id TEXT NOT NULL, node_id TEXT NOT NULL, node_name TEXT, requested_at REAL NOT NULL, updated_at REAL NOT NULL,
        PRIMARY KEY(user_id,node_id)
    );
    CREATE TABLE IF NOT EXISTS dashboard_user_nodes(
        user_id TEXT NOT NULL, node_id TEXT NOT NULL, node_name TEXT, access_state TEXT NOT NULL DEFAULT 'unknown',
        created_at REAL NOT NULL, updated_at REAL NOT NULL,
        PRIMARY KEY(user_id,node_id)
    );
    """)
    # Backfill durable dashboard relationships from historical access requests.
    # Authorization and visibility are intentionally separate: revoking local
    # access must not make a computer disappear from the user's dashboard.
    try:
        db.execute("""INSERT OR IGNORE INTO dashboard_user_nodes(user_id,node_id,node_name,access_state,created_at,updated_at)
                      SELECT user_id,target,target,'unknown',created_at,created_at FROM audit_logs
                       WHERE action='node.access_request' AND target IS NOT NULL AND target<>''""")
    except sqlite3.OperationalError:
        pass
    db.execute("""INSERT OR IGNORE INTO dashboard_user_nodes(user_id,node_id,node_name,access_state,created_at,updated_at)
                  SELECT user_id,node_id,node_name,'pending',requested_at,updated_at FROM dashboard_pending_node_access""")


def _landing_html() -> str:
    css_marker = '/* Lucas public landing */'
    css_start = DASHBOARD_HTML.index(css_marker)
    css_end = DASHBOARD_HTML.index('</style>', css_start)
    landing_css = DASHBOARD_HTML[css_start:css_end]
    section_start = DASHBOARD_HTML.index('<section id="landing" class="landing">')
    section_end = DASHBOARD_HTML.index('\n<div id="auth"', section_start)
    landing = DASHBOARD_HTML[section_start:section_end]
    landing = landing.replace('onclick="openAuth()"', 'onclick="location.href=\'/dashboard\'"')
    seo_copy = """<section aria-label="About Lucas MCP" style="max-width:980px;margin:0 auto;padding:40px 28px 90px;color:#9aa4bd;font:15px/1.8 Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif"><h2 style="color:#f5f7ff;font-size:28px;margin:0 0 12px">Lucas MCP computer connector</h2><p>Lucas MCP is a secure bridge between MCP-compatible AI assistants and your computer. Connect ChatGPT, Claude, Gemini and other AI tools to work with files, projects, browsers, terminals and desktop applications while local permissions remain under your control.</p><p>Lucas is designed for model-agnostic computer automation and remote access, with activity visibility and local permission boundaries instead of unrestricted cloud-side control.</p></section>"""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<meta name="theme-color" content="#05070d" />
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1" />
<meta name="googlebot" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1" />
<meta name="description" content="Lucas MCP securely connects ChatGPT, Claude, Gemini and other MCP-compatible AI assistants to your computer for files, browser, terminal and desktop automation without extra execution tokens." />
<link rel="canonical" href="https://lucasmcp.com/" />
<link rel="icon" type="image/png" sizes="32x32" href="/assets/lucas-logo-square.png?v=20260903" />
<link rel="shortcut icon" type="image/png" href="/assets/lucas-logo-square.png?v=20260903" />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="Lucas MCP" />
<meta property="og:title" content="Lucas MCP — Connect Any AI to Your Computer" />
<meta property="og:description" content="Secure MCP computer connector for ChatGPT, Claude, Gemini and other AI assistants. Control files, browser, terminal and desktop with local permissions." />
<meta property="og:url" content="https://lucasmcp.com/" />
<meta property="og:image" content="https://lucasmcp.com/assets/lucas-logo-square.png" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="Lucas MCP — Connect Any AI to Your Computer" />
<meta name="twitter:description" content="Secure MCP computer connector for ChatGPT, Claude, Gemini and other AI assistants." />
<meta name="twitter:image" content="https://lucasmcp.com/assets/lucas-logo-square.png" />
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"SoftwareApplication","name":"Lucas MCP","alternateName":"Lucas","url":"https://lucasmcp.com/","applicationCategory":"DeveloperApplication","operatingSystem":"Windows; macOS; Linux","description":"Lucas MCP securely connects MCP-compatible AI assistants such as ChatGPT, Claude and Gemini to computers for files, browser, terminal and desktop automation with local permission controls.","image":"https://lucasmcp.com/assets/lucas-logo-square.png","offers":{{"@type":"Offer","price":"0","priceCurrency":"USD"}}}}</script>
<title>Lucas MCP — Connect Any AI to Your Computer</title>
<style>
*{{box-sizing:border-box}}html{{scroll-behavior:smooth;background:#05070d}}body{{margin:0;background:#05070d}}button{{font:inherit}}
{landing_css}
</style>
</head>
<body>{landing}<script>
if((navigator.language||'en').toLowerCase().startsWith('zh')){{document.documentElement.lang='zh-CN';const Z={{'Capabilities':'功能','Security':'安全','How it works':'工作原理','Sign in':'登录','Dashboard':'控制台','Connect your computer':'连接电脑','See how it works ↓':'查看工作原理 ↓','Model agnostic':'不限模型','Cross-platform':'跨平台','Token-free execution':'无额外执行 Token','WHAT LUCAS UNLOCKS':'LUCAS 能做什么','Your AI can finally':'你的 AI 终于可以','do the work.':'真正执行工作。','Terminal & Code':'终端与代码','Files & Projects':'文件与项目','Browser':'浏览器','Computer Use':'电脑操作','Remote Access':'远程访问','A DIFFERENT ARCHITECTURE':'不同的架构','Token-free':'无额外 Token','execution.':'执行。','CONTROL WITHOUT COMPROMISE':'安全控制，不做妥协','Your computer.':'你的电脑。','Your boundaries.':'你的边界。','Project-scoped access':'项目范围访问','Local permission control':'本地权限控制','OAuth-secured MCP':'OAuth 安全 MCP','Activity visibility':'操作记录可见','THREE STEPS':'三个步骤','From AI to action.':'从 AI 到实际执行。','Connect a computer':'连接电脑','Add Lucas MCP':'添加 Lucas MCP','Start working':'开始工作','THE BRIDGE IS READY':'连接已经准备好','Any AI.':'任何 AI。','Any computer.':'任何电脑。','Get started with Lucas':'开始使用 Lucas'}};const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);const a=[];while(w.nextNode())a.push(w.currentNode);for(const n of a){{const t=n.nodeValue.trim();if(Z[t])n.nodeValue=n.nodeValue.replace(t,Z[t])}}}}
</script>{seo_copy}</body>
</html>"""


def _dashboard_html() -> str:
    html = DASHBOARD_HTML
    turnstile_site_key = os.getenv("GWC_TURNSTILE_SITE_KEY", "").strip()
    html = html.replace("__TURNSTILE_SITE_KEY__", turnstile_site_key).replace("__TURNSTILE_CLASS__", "" if turnstile_site_key else "hidden")
    css_marker = '/* Lucas public landing */'
    css_start = html.index(css_marker)
    css_end = html.index('</style>', css_start)
    html = html[:css_start] + html[css_end:]
    section_start = html.index('<section id="landing" class="landing">')
    section_end = html.index('\n<div id="auth"', section_start)
    html = html[:section_start] + html[section_end + 1:]
    html = html.replace('<head>', '<head>\n<meta name="robots" content="noindex,nofollow,noarchive" />', 1)
    return html


async def home(request: Request):
    html = _landing_html()
    try:
        _auth_user(request)
        html = html.replace('Sign in <span>→</span>', 'Dashboard <span>→</span>', 1)
    except Exception:
        pass
    return HTMLResponse(html)


async def dashboard(_: Request):
    return HTMLResponse(_dashboard_html(), headers={"X-Robots-Tag": "noindex, nofollow, noarchive"})


async def admin_page(request: Request):
    try:
        user = _auth_user(request)
    except Exception:
        return RedirectResponse("/dashboard", status_code=302)
    if user.role not in {"admin", "super_admin"}:
        return RedirectResponse("/dashboard", status_code=302)
    return HTMLResponse(_dashboard_html(), headers={"X-Robots-Tag": "noindex, nofollow, noarchive"})


async def robots_txt(_: Request):
    body = """User-agent: *
Allow: /
Disallow: /dashboard
Disallow: /nodes
Disallow: /ai-connections
Disallow: /logs
Disallow: /account
Disallow: /admin
Disallow: /api/
Disallow: /oauth/

Sitemap: https://lucasmcp.com/sitemap.xml
"""
    return PlainTextResponse(body, media_type="text/plain")


async def sitemap_xml(_: Request):
    body = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://lucasmcp.com/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
"""
    return Response(body, media_type="application/xml")


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
    authorized_nodes = await gateway.registry.list(user)
    now = time.time()
    with _db() as db:
        _ensure_dashboard_metadata_schema(db)
        aliases = {r["node_id"]: r["display_name"] for r in db.execute("SELECT node_id,display_name FROM dashboard_node_metadata WHERE user_id=?", (user.id,)).fetchall() if r["display_name"]}
        pending = {r["node_id"]: r for r in db.execute("SELECT node_id,node_name,requested_at,updated_at FROM dashboard_pending_node_access WHERE user_id=?", (user.id,)).fetchall()}
        for node in authorized_nodes:
            node_id = str(node.get("node_id") or "")
            name = str(node.get("name") or node_id)
            db.execute("INSERT INTO dashboard_user_nodes(user_id,node_id,node_name,access_state,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,node_id) DO UPDATE SET node_name=excluded.node_name,access_state='authorized',updated_at=excluded.updated_at", (user.id,node_id,name,"authorized",now,now))
            db.execute("DELETE FROM dashboard_pending_node_access WHERE user_id=? AND node_id=?", (user.id,node_id))
        links = db.execute("SELECT node_id,node_name,access_state,created_at,updated_at FROM dashboard_user_nodes WHERE user_id=? ORDER BY updated_at DESC", (user.id,)).fetchall()

    nodes_by_id = {str(node.get("node_id")): node for node in authorized_nodes}
    for node in authorized_nodes:
        node["authorized"] = True
        node["access_state"] = "authorized"
        node["display_name"] = aliases.get(node["node_id"]) or node.get("name") or node["node_id"]

    for row in links:
        node_id = str(row["node_id"])
        if node_id in nodes_by_id:
            continue
        live = gateway.registry.nodes.get(node_id)
        name = str(row["node_name"] or (live.name if live else node_id))
        pending_row = pending.get(node_id)
        access_state = "pending" if pending_row else str(row["access_state"] or "unknown")
        if live and not pending_row:
            try:
                checked = await gateway.registry.rpc(node_id, user.id, "access.check", {}, actor=gateway._actor(user), timeout=3.0)
            except Exception:
                checked = None
            if isinstance(checked, dict) and checked.get("authorized"):
                gateway.bindings.upsert(user.id, node_id)
                access_state = "authorized"
                node = {"node_id":node_id,"name":live.name,"online":True,"last_seen":live.last_seen,"authorized":True,"access_state":"authorized","preset":str(checked.get("preset") or "request_approval"),"allowed_roots":[str(v) for v in checked.get("allowed_roots") or []]}
                node["display_name"] = aliases.get(node_id) or node["name"] or node_id
                authorized_nodes.append(node)
                with _db() as db:
                    _ensure_dashboard_metadata_schema(db)
                    db.execute("UPDATE dashboard_user_nodes SET node_name=?,access_state='authorized',updated_at=? WHERE user_id=? AND node_id=?", (live.name,now,user.id,node_id))
                    db.execute("DELETE FROM dashboard_pending_node_access WHERE user_id=? AND node_id=?", (user.id,node_id))
                continue
            if isinstance(checked, dict):
                access_state = "unauthorized"
                with _db() as db:
                    _ensure_dashboard_metadata_schema(db)
                    db.execute("UPDATE dashboard_user_nodes SET node_name=?,access_state='unauthorized',updated_at=? WHERE user_id=? AND node_id=?", (live.name,now,user.id,node_id))
        authorized_nodes.append({"node_id":node_id,"name":name,"display_name":aliases.get(node_id) or name,"pending":access_state=="pending","authorized":access_state=="authorized","access_state":access_state,"online":bool(live),"preset":"request_approval","allowed_roots":[],"last_seen":live.last_seen if live else row["updated_at"],"requested_at":pending_row["requested_at"] if pending_row else None})
    return JSONResponse({"nodes": authorized_nodes})


async def api_node_name(request: Request):
    user = _auth_user(request)
    node_id = unquote(request.path_params["node_id"])
    nodes = await gateway.registry.list(user)
    node = next((n for n in nodes if n.get("node_id") == node_id), None)
    if not node:
        return JSONResponse({"error": "Node not found"}, status_code=404)
    body = await request.json()
    name = str(body.get("name") or "").strip()[:100]
    with _db() as db:
        _ensure_dashboard_metadata_schema(db)
        if name:
            db.execute("INSERT INTO dashboard_node_metadata(user_id,node_id,display_name,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id,node_id) DO UPDATE SET display_name=excluded.display_name,updated_at=excluded.updated_at", (user.id,node_id,name,time.time()))
        else:
            db.execute("DELETE FROM dashboard_node_metadata WHERE user_id=? AND node_id=?", (user.id,node_id))
    gateway.auth.audit(user.id, "node.rename", node_id, {"display_name": name})
    return JSONResponse({"ok": True, "display_name": name or node.get("name") or node_id})


async def api_request_node_access(request: Request):
    user = _auth_user(request)
    body = await request.json()
    node_id = str(body.get("node_id") or "").strip()
    connection_code = str(body.get("connection_code") or "").strip()
    if not node_id:
        return JSONResponse({"error": "Node ID is required"}, status_code=400)
    if len(connection_code) != 8 or not connection_code.isdigit():
        return JSONResponse({"error": "An 8-digit Connection Code is required"}, status_code=400)
    try:
        gateway.registry.require_online(node_id)
        if not gateway.registration_security.allow(f"node-access:{user.id}:{node_id}", 5, 60):
            return JSONResponse({"error": "Too many connection attempts. Try again in a minute."}, status_code=429)
        result = await gateway.registry.rpc(node_id, user.id, "access.request", {"connection_code": connection_code}, actor=gateway._actor(user), timeout=180.0)
        if isinstance(result, dict) and result.get("authorized"):
            gateway.bindings.upsert(user.id, node_id)
            live=gateway.registry.nodes.get(node_id); node_name=live.name if live else node_id; now=time.time()
            with _db() as db:
                _ensure_dashboard_metadata_schema(db)
                db.execute("INSERT INTO dashboard_user_nodes(user_id,node_id,node_name,access_state,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,node_id) DO UPDATE SET node_name=excluded.node_name,access_state='authorized',updated_at=excluded.updated_at", (user.id,node_id,node_name,"authorized",now,now))
                db.execute("DELETE FROM dashboard_pending_node_access WHERE user_id=? AND node_id=?", (user.id,node_id))
        elif isinstance(result, dict) and result.get("pending"):
            live=gateway.registry.nodes.get(node_id); node_name=live.name if live else node_id; now=time.time()
            with _db() as db:
                _ensure_dashboard_metadata_schema(db)
                db.execute("INSERT INTO dashboard_user_nodes(user_id,node_id,node_name,access_state,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,node_id) DO UPDATE SET node_name=excluded.node_name,access_state='pending',updated_at=excluded.updated_at", (user.id,node_id,node_name,"pending",now,now))
                db.execute("INSERT INTO dashboard_pending_node_access(user_id,node_id,node_name,requested_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id,node_id) DO UPDATE SET node_name=excluded.node_name,updated_at=excluded.updated_at", (user.id,node_id,node_name,float(result.get("requested_at") or now),now))
        gateway.auth.audit(user.id, "node.access_request", node_id, {"authorized": bool(isinstance(result, dict) and result.get("authorized")), "pending": bool(isinstance(result, dict) and result.get("pending"))})
        return JSONResponse(result if isinstance(result, dict) else {"authorized": False})
    except (RuntimeError, PermissionError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_node_logs(request: Request):
    user = _auth_user(request)
    node_id = unquote(request.path_params["node_id"])
    try:
        gateway.registry.require_online(node_id)
        limit = max(20, min(int(request.query_params.get("limit", "250")), 1000))
        result = await gateway.registry.rpc(node_id, user.id, "node.logs", {"limit": limit}, actor=gateway._actor(user), timeout=30)
        return JSONResponse(result)
    except (RuntimeError, PermissionError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_folders(request: Request):
    user = _auth_user(request)
    node_id = unquote(request.path_params["node_id"])
    path = request.query_params.get("path")
    try:
        gateway.registry.require_online(node_id)
        result = await gateway.registry.rpc(node_id, user.id, "workspace.browse", {"path": path} if path else {}, actor=gateway._actor(user))
        return JSONResponse(result)
    except (RuntimeError, PermissionError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_ai_connections(request: Request):
    user = _auth_user(request)
    with _db() as db:
        _ensure_dashboard_metadata_schema(db)
        rows = db.execute(
            """SELECT c.client_id,c.client_name,c.created_at,m.display_name,m.note
               FROM oauth_clients c
               JOIN oauth_client_users cu ON cu.client_id=c.client_id
               LEFT JOIN dashboard_ai_metadata m ON m.client_id=c.client_id AND m.user_id=cu.user_id
              WHERE cu.user_id=?
              ORDER BY cu.authorized_at DESC,c.created_at DESC""",
            (user.id,),
        ).fetchall()
    return JSONResponse({"clients": [{"client_id": r["client_id"], "client_name": r["client_name"], "display_name": r["display_name"] or r["client_name"], "note": r["note"] or "", "created_at": r["created_at"]} for r in rows]})


async def api_ai_connection(request: Request):
    user = _auth_user(request)
    client_id = unquote(request.path_params["client_id"])
    with _db() as db:
        _ensure_dashboard_metadata_schema(db)
        row = db.execute("SELECT c.client_name FROM oauth_clients c JOIN oauth_client_users cu ON cu.client_id=c.client_id WHERE c.client_id=? AND cu.user_id=?", (client_id,user.id)).fetchone()
        if not row:
            return JSONResponse({"error": "AI connection not found"}, status_code=404)
        if request.method == "DELETE":
            db.execute("DELETE FROM oauth_refresh_tokens WHERE client_id=? AND user_id=?", (client_id,user.id))
            db.execute("DELETE FROM oauth_codes WHERE client_id=? AND user_id=?", (client_id,user.id))
            db.execute("DELETE FROM oauth_client_users WHERE client_id=? AND user_id=?", (client_id,user.id))
            db.execute("DELETE FROM dashboard_ai_metadata WHERE client_id=? AND user_id=?", (client_id,user.id))
            gateway.auth.audit(user.id, "oauth.disconnect", client_id)
            return JSONResponse({"ok": True})
        body = await request.json()
        display_name = str(body.get("display_name") or "").strip()[:100]
        note = str(body.get("note") or "").strip()[:500]
        db.execute("INSERT INTO dashboard_ai_metadata(user_id,client_id,display_name,note,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id,client_id) DO UPDATE SET display_name=excluded.display_name,note=excluded.note,updated_at=excluded.updated_at", (user.id,client_id,display_name or None,note or None,time.time()))
    gateway.auth.audit(user.id, "oauth.connection_update", client_id, {"display_name": display_name, "has_note": bool(note)})
    return JSONResponse({"ok": True, "display_name": display_name or row["client_name"], "note": note})



async def api_task_runs(request: Request):
    user = _auth_user(request)
    limit = max(1, min(int(request.query_params.get("limit", "100")), 500))
    node_id = request.query_params.get("node_id", "").strip() or None
    return JSONResponse({"runs": gateway.task_runs.list_runs(user.id, node_id=node_id, limit=limit)})

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


async def brand_asset(request: Request):
    name = str(request.path_params.get("name") or "")
    if name not in {"lucas-logo-horizontal.png", "lucas-logo-horizontal-white.png", "lucas-logo-square.png"}:
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(
        BRAND_ASSET_DIR / name,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


routes = [
    Route("/robots.txt", robots_txt, methods=["GET"]),
    Route("/sitemap.xml", sitemap_xml, methods=["GET"]),
    Route("/assets/{name:str}", brand_asset, methods=["GET"]),
    Route("/", home, methods=["GET"]),
    Route("/dashboard", dashboard, methods=["GET"]),
    Route("/nodes", dashboard, methods=["GET"]),
    Route("/ai-connections", dashboard, methods=["GET"]),
    Route("/logs", dashboard, methods=["GET"]),
    Route("/account", dashboard, methods=["GET"]),
    Route("/admin", admin_page, methods=["GET"]),
    Route("/admin/users", admin_page, methods=["GET"]),
    Route("/admin/usage", admin_page, methods=["GET"]),
    Route("/admin/nodes", admin_page, methods=["GET"]),
    Route("/admin/operations", admin_page, methods=["GET"]),
    Route("/admin/subscriptions", admin_page, methods=["GET"]),
    Route("/admin/system", admin_page, methods=["GET"]),
    Route("/download/Lucas-Node.ps1", download_lucas_node, methods=["GET"]),
    Route("/download/Lucas-Node.bat", download_lucas_launcher, methods=["GET"]),
    Route("/api/logout", api_logout, methods=["POST"]),
    Route("/api/nodes", api_nodes, methods=["GET"]),
    Route("/api/nodes/request-access", api_request_node_access, methods=["POST"]),
    Route("/api/nodes/{node_id}/logs", api_node_logs, methods=["GET"]),
    Route("/api/nodes/{node_id}/folders", api_folders, methods=["GET"]),
    Route("/api/nodes/{node_id}/name", api_node_name, methods=["PUT"]),
    Route("/api/ai-connections", api_ai_connections, methods=["GET"]),
    Route("/api/ai-connections/{client_id}", api_ai_connection, methods=["PUT","DELETE"]),
    Route("/api/task-runs", api_task_runs, methods=["GET"]),
    Route("/api/logs", api_logs, methods=["GET"]),
    *admin_routes,
    Mount("/", app=gateway.app),
]

app = Starlette(routes=routes)


def main() -> None:
    uvicorn.run(app, host=gateway.settings.host, port=gateway.settings.port, log_level="info")


if __name__ == "__main__":
    main()
