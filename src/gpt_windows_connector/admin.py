from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import gateway
from .entitlements import snapshot


def _db() -> sqlite3.Connection:
    db = sqlite3.connect(gateway.db_path, timeout=30)
    db.row_factory = sqlite3.Row
    return db


def _admin(request: Request):
    token = request.cookies.get("gwc_access_token", "")
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    user = gateway.auth.verify_token(token)
    if user.role not in {"admin", "super_admin"}:
        raise PermissionError("Admin access required")
    return user



def _ensure_entitlement_override_schema(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS entitlement_overrides(
        user_id TEXT PRIMARY KEY, bonus_requests INTEGER NOT NULL DEFAULT 0,
        bonus_nodes INTEGER NOT NULL DEFAULT 0, bonus_ai_accounts INTEGER NOT NULL DEFAULT 0,
        expires_at REAL, updated_at REAL NOT NULL DEFAULT 0
    )""")
    cols={str(r[1]) for r in db.execute("PRAGMA table_info(entitlement_overrides)").fetchall()}
    if "expires_at" not in cols:
        db.execute("ALTER TABLE entitlement_overrides ADD COLUMN expires_at REAL")

def _safe_details(raw: str | None) -> dict:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    blocked = {"password", "token", "access_token", "authorization", "cookie", "clipboard", "content", "command", "stdout", "stderr"}
    return {k: ("[redacted]" if k.lower() in blocked else v) for k, v in data.items()}


def _error(exc: Exception):
    code = 403 if isinstance(exc, PermissionError) else 400
    return JSONResponse({"error": str(exc)}, status_code=code)


async def dashboard(request: Request):
    try:
        _admin(request)
        now = time.time(); day = now - 86400; week = now - 7 * 86400; month = now - 30 * 86400
        with _db() as db:
            users = db.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
            new_7d = db.execute("SELECT COUNT(*) n FROM users WHERE created_at>=?", (week,)).fetchone()["n"]
            active_7d = db.execute("SELECT COUNT(DISTINCT user_id) n FROM audit_logs WHERE created_at>=?", (week,)).fetchone()["n"]
            nodes = db.execute("SELECT COUNT(*) n FROM nodes").fetchone()["n"]
            ops_today = db.execute("SELECT COUNT(*) n FROM task_steps WHERE started_at>=?", (day,)).fetchone()["n"]
            ops_30d = db.execute("SELECT COUNT(*) n FROM task_steps WHERE started_at>=?", (month,)).fetchone()["n"]
            paid = db.execute("SELECT COUNT(*) n FROM subscriptions WHERE status='active' AND plan!='free'").fetchone()["n"]
            usage = db.execute("SELECT COUNT(*) operations,SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) success,SUM(CASE WHEN status!='success' THEN 1 ELSE 0 END) errors,COALESCE(SUM(duration_ms),0)/1000.0 seconds FROM task_steps WHERE started_at>=?", (month,)).fetchone()
            recent = db.execute("SELECT a.created_at,a.action,a.target,u.email FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 12").fetchall()
        total_done = int(usage["success"] or 0) + int(usage["errors"] or 0)
        return JSONResponse({"users": users, "new_users_7d": new_7d, "active_users_7d": active_7d, "nodes": nodes, "online_nodes": len(gateway.registry.nodes), "operations_today": ops_today, "operations_30d": int(ops_30d), "requests_30d": int(ops_30d), "execution_seconds_30d": float(usage["seconds"] or 0), "success_rate": round((int(usage["success"] or 0) / total_done * 100), 2) if total_done else 100.0, "paid_users": paid, "recent": [dict(r) for r in recent]})
    except Exception as exc: return _error(exc)


async def users(request: Request):
    try:
        _admin(request)
        q = request.query_params.get("q", "").strip()
        with _db() as db:
            sql = """SELECT u.id,u.email,u.name,u.provider,u.role,u.status,u.created_at,u.last_login_at,
                COALESCE(s.plan,'free') plan,COALESCE(s.status,'inactive') subscription_status,
                (SELECT COUNT(*) FROM user_node_bindings b WHERE b.user_id=u.id) node_count,
                (SELECT COUNT(*) FROM task_steps t WHERE t.owner_id=u.id AND t.started_at>=?) operations_30d
                FROM users u LEFT JOIN subscriptions s ON s.user_id=u.id"""
            params: list[object] = [time.time()-30*86400]
            if q:
                sql += " WHERE u.email LIKE ? OR u.name LIKE ?"; params += [f"%{q}%", f"%{q}%"]
            sql += " ORDER BY u.created_at DESC LIMIT 500"
            rows = db.execute(sql, params).fetchall()
        return JSONResponse({"users": [dict(r) for r in rows]})
    except Exception as exc: return _error(exc)


async def user_detail(request: Request):
    try:
        _admin(request); user_id = request.path_params["user_id"]
        with _db() as db:
            user = db.execute("SELECT id,email,name,provider,role,status,created_at,last_login_at FROM users WHERE id=?", (user_id,)).fetchone()
            if not user: return JSONResponse({"error": "User not found"}, status_code=404)
            sub = db.execute("SELECT * FROM subscriptions WHERE user_id=?", (user_id,)).fetchone()
            _ensure_entitlement_override_schema(db)
            override = db.execute("SELECT bonus_requests,bonus_nodes,bonus_ai_accounts,expires_at,updated_at FROM entitlement_overrides WHERE user_id=?",(user_id,)).fetchone()
            nodes = db.execute("SELECT n.node_id,n.name,n.updated_at FROM user_node_bindings b JOIN nodes n ON n.node_id=b.node_id WHERE b.user_id=? ORDER BY b.approved_at ASC",(user_id,)).fetchall()
            ops = db.execute("SELECT id,action,target,details,started_at AS created_at,status FROM task_steps WHERE owner_id=? ORDER BY started_at DESC LIMIT 100", (user_id,)).fetchall()
            counts = db.execute("SELECT COUNT(*) total,SUM(CASE WHEN started_at>=? THEN 1 ELSE 0 END) last30 FROM task_steps WHERE owner_id=?", (time.time()-30*86400,user_id)).fetchone()
        ent=snapshot(gateway.db_path,user_id).as_dict()
        override_data=dict(override) if override else {"bonus_requests":0,"bonus_nodes":0,"bonus_ai_accounts":0,"expires_at":None,"updated_at":None}
        override_data["expired"]=bool(override_data.get("expires_at") and float(override_data["expires_at"])<=time.time())
        return JSONResponse({"user": dict(user), "subscription": dict(sub) if sub else {"plan":"free","status":"inactive"}, "entitlements":ent, "admin_overrides":override_data, "nodes": [dict(r) for r in nodes], "usage": dict(counts), "operations": [{**dict(r), "details": _safe_details(r["details"])} for r in ops]})
    except Exception as exc: return _error(exc)


async def update_user(request: Request):
    try:
        actor = _admin(request); user_id = request.path_params["user_id"]; body = await request.json(); now=time.time()
        with _db() as db:
            if "status" in body:
                status = str(body["status"]);
                if status not in {"active","disabled"}: raise ValueError("Invalid status")
                db.execute("UPDATE users SET status=?,updated_at=? WHERE id=?", (status,now,user_id))
            if "role" in body:
                if actor.role != "super_admin": raise PermissionError("Only super admins can change roles")
                role=str(body["role"]);
                if role not in {"user","admin","super_admin"}: raise ValueError("Invalid role")
                db.execute("UPDATE users SET role=?,updated_at=? WHERE id=?", (role,now,user_id))
            if "plan" in body:
                plan=str(body["plan"]);
                if plan not in {"free","pro","pro_plus"}: raise ValueError("Invalid plan")
                sub_status=str(body.get("subscription_status", "active" if plan != "free" else "inactive"))
                db.execute("INSERT INTO subscriptions(user_id,plan,status,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET plan=excluded.plan,status=excluded.status,expansion_quantity=CASE WHEN excluded.plan='pro_plus' THEN expansion_quantity ELSE 0 END,updated_at=excluded.updated_at", (user_id,plan,sub_status,now))
            override_fields={k:max(0,int(body[k])) for k in ("bonus_requests","bonus_nodes","bonus_ai_accounts") if k in body}
            expiry_supplied="override_expires_at" in body
            if override_fields or expiry_supplied:
                _ensure_entitlement_override_schema(db)
                current=db.execute("SELECT bonus_requests,bonus_nodes,bonus_ai_accounts,expires_at FROM entitlement_overrides WHERE user_id=?",(user_id,)).fetchone()
                values={"bonus_requests":int(current[0] or 0) if current else 0,"bonus_nodes":int(current[1] or 0) if current else 0,"bonus_ai_accounts":int(current[2] or 0) if current else 0}
                values.update(override_fields)
                expires=(float(current[3]) if current and current[3] not in (None,0,0.0) else None)
                if expiry_supplied:
                    raw=body.get("override_expires_at")
                    expires=None if raw in (None,"",0,0.0) else float(raw)
                    if expires is not None and expires <= now: raise ValueError("Expiration must be in the future")
                if not any(values.values()): expires=None
                db.execute("INSERT INTO entitlement_overrides(user_id,bonus_requests,bonus_nodes,bonus_ai_accounts,expires_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET bonus_requests=excluded.bonus_requests,bonus_nodes=excluded.bonus_nodes,bonus_ai_accounts=excluded.bonus_ai_accounts,expires_at=excluded.expires_at,updated_at=excluded.updated_at",(user_id,values["bonus_requests"],values["bonus_nodes"],values["bonus_ai_accounts"],expires,now))
        gateway.auth.audit(actor.id, "admin.user_update", user_id, {"fields": sorted(body.keys())})
        return JSONResponse({"ok": True})
    except Exception as exc: return _error(exc)


async def usage(request: Request):
    try:
        _admin(request); since=time.time()-30*86400
        with _db() as db:
            rows=db.execute("SELECT action,COUNT(*) n FROM task_steps WHERE started_at>=? GROUP BY action ORDER BY n DESC",(since,)).fetchall()
            daily=db.execute("SELECT date(started_at,'unixepoch') day,COUNT(*) requests,COUNT(*) operations,SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) success,SUM(CASE WHEN status!='success' THEN 1 ELSE 0 END) errors,COALESCE(SUM(duration_ms),0)/1000.0 seconds FROM task_steps WHERE started_at>=? GROUP BY date(started_at,'unixepoch') ORDER BY day",(since,)).fetchall()
            totals=db.execute("SELECT COUNT(*) requests,COUNT(*) operations,SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) success,SUM(CASE WHEN status!='success' THEN 1 ELSE 0 END) errors,COALESCE(SUM(duration_ms),0)/1000.0 seconds FROM task_steps WHERE started_at>=?",(since,)).fetchone()
            top_users=db.execute("SELECT u.email,COUNT(*) n FROM task_steps t JOIN users u ON u.id=t.owner_id WHERE t.started_at>=? GROUP BY t.owner_id ORDER BY n DESC LIMIT 20",(since,)).fetchall()
        groups=Counter()
        for r in rows:
            a=r["action"]; groups[a.split('.')[0] if '.' in a else a]+=r["n"]
        done=int(totals["success"] or 0)+int(totals["errors"] or 0)
        return JSONResponse({"requests_30d":int(totals["requests"] or 0),"operations_30d":int(totals["operations"] or 0),"execution_seconds_30d":float(totals["seconds"] or 0),"success_rate":round((int(totals["success"] or 0)/done*100),2) if done else 100.0, "errors_30d":int(totals["errors"] or 0), "by_tool": dict(groups), "by_action": [dict(r) for r in rows], "daily": [dict(r) for r in daily], "top_users": [dict(r) for r in top_users]})
    except Exception as exc: return _error(exc)


async def nodes(request: Request):
    try:
        _admin(request); online=set(gateway.registry.nodes)
        with _db() as db:
            rows=db.execute("SELECT n.node_id,n.name,n.updated_at,n.allowed_roots FROM nodes n ORDER BY n.updated_at DESC").fetchall()
        data=[]
        for r in rows:
            d=dict(r); d["online"]=d["node_id"] in online; d["platform"]="windows"; d["allowed_folder_count"]=len(json.loads(d.get("allowed_roots") or "[]")); d.pop("allowed_roots",None); data.append(d)
        return JSONResponse({"nodes":data})
    except Exception as exc: return _error(exc)


async def operations(request: Request):
    try:
        _admin(request); limit=max(1,min(int(request.query_params.get("limit","200")),1000)); user=request.query_params.get("user",""); action=request.query_params.get("action",""); status=request.query_params.get("status","")
        sql="SELECT t.id,t.owner_id AS user_id,u.email,t.action,t.target,t.details,t.started_at AS created_at,t.status FROM task_steps t LEFT JOIN users u ON u.id=t.owner_id WHERE 1=1"; params=[]
        if user: sql+=" AND (u.email LIKE ? OR t.owner_id=?)"; params += [f"%{user}%",user]
        if action: sql+=" AND t.action LIKE ?"; params.append(f"%{action}%")
        sql+=" ORDER BY t.id DESC LIMIT ?"; params.append(limit)
        with _db() as db: rows=db.execute(sql,params).fetchall()
        out=[]
        for r in rows:
            d=dict(r); d["details"]=_safe_details(d.get("details")); d["status"]=d.get("status") or d["details"].get("status","success"); out.append(d)
        if status: out=[d for d in out if d["status"]==status]
        return JSONResponse({"operations":out})
    except Exception as exc: return _error(exc)


async def subscriptions(request: Request):
    try:
        _admin(request)
        with _db() as db:
            rows=db.execute("SELECT u.id user_id,u.email,COALESCE(s.plan,'free') plan,COALESCE(s.status,'inactive') status,s.billing_provider,s.billing_customer_id,s.stripe_subscription_id,COALESCE(s.expansion_quantity,0) expansion_quantity,COALESCE(s.bonus_requests,0) bonus_requests,s.current_period_end,s.started_at,s.ends_at FROM users u LEFT JOIN subscriptions s ON s.user_id=u.id ORDER BY u.created_at DESC").fetchall()
        return JSONResponse({"subscriptions":[dict(r) for r in rows]})
    except Exception as exc: return _error(exc)


async def system(request: Request):
    try:
        _admin(request)
        with _db() as db:
            db.execute("SELECT 1").fetchone(); users_n=db.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]; nodes_n=db.execute("SELECT COUNT(*) n FROM nodes").fetchone()["n"]
        return JSONResponse({"gateway":"healthy","database":"healthy","online_nodes":len(gateway.registry.nodes),"total_nodes":nodes_n,"users":users_n,"server_time":time.time()})
    except Exception as exc: return _error(exc)


admin_routes = [
    Route("/api/admin/dashboard", dashboard, methods=["GET"]),
    Route("/api/admin/users", users, methods=["GET"]),
    Route("/api/admin/users/{user_id}", user_detail, methods=["GET"]),
    Route("/api/admin/users/{user_id}", update_user, methods=["PUT"]),
    Route("/api/admin/usage", usage, methods=["GET"]),
    Route("/api/admin/nodes", nodes, methods=["GET"]),
    Route("/api/admin/operations", operations, methods=["GET"]),
    Route("/api/admin/subscriptions", subscriptions, methods=["GET"]),
    Route("/api/admin/system", system, methods=["GET"]),
]
