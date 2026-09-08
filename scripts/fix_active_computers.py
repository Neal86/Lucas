from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'/'gpt_windows_connector'

ent='''from __future__ import annotations

import calendar
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PLANS: dict[str, dict[str, Any]] = {
    "free": {"name": "Free", "price": 0.0, "requests": 1_000, "nodes": 1, "ai_accounts": 1},
    "pro": {"name": "Pro", "price": 9.99, "requests": 25_000, "nodes": 3, "ai_accounts": 1},
    "pro_plus": {"name": "Pro+", "price": 19.99, "requests": 100_000, "nodes": 6, "ai_accounts": 3},
}
EXPANSION = {"price": 14.99, "requests": 100_000, "nodes": 6, "ai_accounts": 1}
ACTIVE_STATUSES = {"active", "trialing", "past_due"}

@dataclass(frozen=True)
class Entitlements:
    plan: str; plan_name: str; status: str; expansion_quantity: int
    request_limit: int; node_limit: int; ai_account_limit: int
    requests_used: int; nodes_used: int; ai_accounts_used: int
    period_start: float; period_end: float; renewal_at: float | None
    cancel_at_period_end: bool; bonus_requests: int; nodes_connected: int = 0
    @property
    def can_buy_expansion(self) -> bool: return self.plan == "pro_plus" and self.status in ACTIVE_STATUSES
    def as_dict(self) -> dict[str, Any]:
        return {"plan":self.plan,"plan_name":self.plan_name,"status":self.status,"expansion_quantity":self.expansion_quantity,"request_limit":self.request_limit,"node_limit":self.node_limit,"ai_account_limit":self.ai_account_limit,"requests_used":self.requests_used,"nodes_used":self.nodes_used,"nodes_connected":self.nodes_connected,"ai_accounts_used":self.ai_accounts_used,"period_start":self.period_start,"period_end":self.period_end,"renewal_at":self.renewal_at,"cancel_at_period_end":self.cancel_at_period_end,"bonus_requests":self.bonus_requests,"can_buy_expansion":self.can_buy_expansion,"request_remaining":max(0,self.request_limit-self.requests_used),"node_remaining":max(0,self.node_limit-self.nodes_used),"ai_account_remaining":max(0,self.ai_account_limit-self.ai_accounts_used)}

def _connect(db_path: Path) -> sqlite3.Connection:
    db=sqlite3.connect(db_path,timeout=30); db.row_factory=sqlite3.Row; return db

def _free_period(now: float) -> tuple[float,float]:
    tm=time.gmtime(now); start=calendar.timegm((tm.tm_year,tm.tm_mon,1,0,0,0,0,0,0))
    end=calendar.timegm((tm.tm_year+1,1,1,0,0,0,0,0,0)) if tm.tm_mon==12 else calendar.timegm((tm.tm_year,tm.tm_mon+1,1,0,0,0,0,0,0))
    return float(start),float(end)

def _count(db: sqlite3.Connection,sql: str,params: tuple[Any,...]) -> int:
    try:
        row=db.execute(sql,params).fetchone(); return int(row[0]) if row else 0
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc).lower(): raise
        return 0

def _ensure_active_schema(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS user_active_nodes(
        user_id TEXT NOT NULL,node_id TEXT NOT NULL,activated_at REAL NOT NULL,manual INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(user_id,node_id)
    )""")

def _plan_state(db: sqlite3.Connection,user_id: str,now: float) -> tuple[str,str,int,int,float,float,bool,dict[str,Any]]:
    row=db.execute("SELECT * FROM subscriptions WHERE user_id=?",(user_id,)).fetchone()
    status=str(row["status"] if row and "status" in row.keys() else "inactive")
    raw=str(row["plan"] if row and "plan" in row.keys() else "free")
    plan=raw if raw in PLANS and status in ACTIVE_STATUSES else "free"
    expansion=int((row["expansion_quantity"] if row and "expansion_quantity" in row.keys() else 0) or 0) if plan=="pro_plus" else 0
    bonus=int((row["bonus_requests"] if row and "bonus_requests" in row.keys() else 0) or 0)
    pstart=float((row["current_period_start"] if row and "current_period_start" in row.keys() else 0) or 0); pend=float((row["current_period_end"] if row and "current_period_end" in row.keys() else 0) or 0)
    if plan=="free" or pstart<=0 or pend<=pstart: pstart,pend=_free_period(now)
    cancel=bool((row["cancel_at_period_end"] if row and "cancel_at_period_end" in row.keys() else 0) or 0)
    return plan,status,expansion,bonus,pstart,pend,cancel,PLANS[plan]

def _bound_ids(db: sqlite3.Connection,user_id: str) -> list[str]:
    try:
        rows=db.execute("SELECT node_id FROM user_node_bindings WHERE user_id=? ORDER BY approved_at DESC,node_id ASC",(user_id,)).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower(): return []
        raise
    return [str(r[0]) for r in rows]

def _sync_active(db: sqlite3.Connection,user_id: str,limit: int,preferred_ids: Iterable[str] | None=None) -> list[str]:
    _ensure_active_schema(db)
    bound=_bound_ids(db,user_id); bound_set=set(bound)
    db.execute("DELETE FROM user_active_nodes WHERE user_id=? AND node_id NOT IN (SELECT node_id FROM user_node_bindings WHERE user_id=?)",(user_id,user_id)) if bound else db.execute("DELETE FROM user_active_nodes WHERE user_id=?",(user_id,))
    if limit<=0 or not bound:
        db.execute("DELETE FROM user_active_nodes WHERE user_id=?",(user_id,)); return []
    rows=db.execute("SELECT node_id,activated_at,manual FROM user_active_nodes WHERE user_id=? ORDER BY manual DESC,activated_at DESC",(user_id,)).fetchall()
    manual=[str(r["node_id"]) for r in rows if int(r["manual"] or 0) and str(r["node_id"]) in bound_set][:limit]
    existing_auto=[str(r["node_id"]) for r in rows if not int(r["manual"] or 0) and str(r["node_id"]) in bound_set]
    preferred=[]
    for v in preferred_ids or []:
        v=str(v)
        if v in bound_set and v not in preferred: preferred.append(v)
    remaining=limit-len(manual)
    candidates=(preferred + existing_auto + bound) if preferred_ids is not None else (existing_auto + bound)
    desired=list(manual)
    for node_id in candidates:
        if node_id not in desired:
            desired.append(node_id)
        if len(desired)>=limit: break
    now=time.time()
    for node_id in list({str(r["node_id"]) for r in rows}-set(desired)):
        db.execute("DELETE FROM user_active_nodes WHERE user_id=? AND node_id=?",(user_id,node_id))
    for node_id in desired:
        if node_id in manual: continue
        db.execute("INSERT INTO user_active_nodes(user_id,node_id,activated_at,manual) VALUES(?,?,?,0) ON CONFLICT(user_id,node_id) DO UPDATE SET activated_at=excluded.activated_at,manual=0",(user_id,node_id,now))
    return desired

def snapshot(db_path: Path,user_id: str,now: float|None=None) -> Entitlements:
    now=float(now or time.time())
    with _connect(db_path) as db:
        plan,status,expansion,bonus,pstart,pend,cancel,base=_plan_state(db,user_id,now)
        req=_count(db,"SELECT COUNT(*) FROM task_steps WHERE owner_id=? AND started_at>=? AND started_at<?",(user_id,pstart,pend))
        ai=_count(db,"SELECT COUNT(*) FROM oauth_client_users WHERE user_id=?",(user_id,))
        node_limit=int(base["nodes"])+expansion*int(EXPANSION["nodes"])
        connected=len(_bound_ids(db,user_id))
        active=len(_sync_active(db,user_id,node_limit))
    return Entitlements(plan,str(base["name"]),status if plan!="free" else "free",expansion,int(base["requests"])+expansion*int(EXPANSION["requests"])+bonus,node_limit,int(base["ai_accounts"])+expansion*int(EXPANSION["ai_accounts"]),req,active,ai,pstart,pend,pend if plan!="free" else None,cancel,bonus,connected)

def ensure_request_capacity(db_path: Path,user_id: str) -> Entitlements:
    e=snapshot(db_path,user_id)
    if e.requests_used>=e.request_limit: raise PermissionError(f"Monthly Request limit reached ({e.requests_used}/{e.request_limit}). {'Add an Expansion Pack' if e.can_buy_expansion else 'Upgrade your plan'} at /billing.")
    return e

def ensure_node_capacity(db_path: Path,user_id: str,node_id: str) -> Entitlements:
    # Connecting/authorizing extra computers is allowed. Plan limits control which
    # computers are active, not whether historical bindings remain visible.
    return snapshot(db_path,user_id)

def ensure_ai_capacity(db_path: Path,user_id: str,client_id: str) -> Entitlements:
    e=snapshot(db_path,user_id)
    with _connect(db_path) as db: exists=db.execute("SELECT 1 FROM oauth_client_users WHERE user_id=? AND client_id=?",(user_id,client_id)).fetchone()
    if not exists and e.ai_accounts_used>=e.ai_account_limit: raise PermissionError(f"AI account limit reached ({e.ai_accounts_used}/{e.ai_account_limit}). {'Add an Expansion Pack' if e.can_buy_expansion else 'Upgrade to Pro+'} at /billing.")
    return e

def active_node_ids(db_path: Path,user_id: str,preferred_node_ids: Iterable[str] | None=None) -> list[str]:
    now=time.time()
    with _connect(db_path) as db:
        plan,status,expansion,bonus,pstart,pend,cancel,base=_plan_state(db,user_id,now)
        limit=int(base["nodes"])+expansion*int(EXPANSION["nodes"])
        return _sync_active(db,user_id,limit,preferred_node_ids)

def set_active_node(db_path: Path,user_id: str,node_id: str) -> list[str]:
    node_id=str(node_id or "").strip()
    if not node_id: raise ValueError("Computer ID is required")
    now=time.time()
    with _connect(db_path) as db:
        plan,status,expansion,bonus,pstart,pend,cancel,base=_plan_state(db,user_id,now)
        limit=int(base["nodes"])+expansion*int(EXPANSION["nodes"])
        bound=set(_bound_ids(db,user_id))
        if node_id not in bound: raise ValueError("Computer is not connected to this account")
        current=_sync_active(db,user_id,limit)
        if node_id in current:
            db.execute("UPDATE user_active_nodes SET manual=1,activated_at=? WHERE user_id=? AND node_id=?",(now,user_id,node_id)); return active_node_ids(db_path,user_id)
        if len(current)>=limit and current:
            rows=db.execute("SELECT node_id,manual,activated_at FROM user_active_nodes WHERE user_id=? ORDER BY manual ASC,activated_at ASC",(user_id,)).fetchall()
            victim=next((str(r["node_id"]) for r in rows if str(r["node_id"])!=node_id),current[-1])
            db.execute("DELETE FROM user_active_nodes WHERE user_id=? AND node_id=?",(user_id,victim))
        db.execute("INSERT INTO user_active_nodes(user_id,node_id,activated_at,manual) VALUES(?,?,?,1) ON CONFLICT(user_id,node_id) DO UPDATE SET activated_at=excluded.activated_at,manual=1",(user_id,node_id,now))
        return _sync_active(db,user_id,limit)

def ensure_node_active(db_path: Path,user_id: str,node_id: str) -> Entitlements:
    e=snapshot(db_path,user_id)
    with _connect(db_path) as db:
        bound=db.execute("SELECT 1 FROM user_node_bindings WHERE user_id=? AND node_id=?",(user_id,node_id)).fetchone()
    if bound and node_id not in active_node_ids(db_path,user_id):
        raise PermissionError(f"This computer is inactive for your plan ({e.node_limit} active computer(s)). Activate it in Computers or upgrade your plan.")
    return e
'''
(SRC/'entitlements.py').write_text(ent,encoding='utf-8')

# webapp imports, online preference, activation API, route
p=SRC/'webapp.py'; s=p.read_text(encoding='utf-8')
s=s.replace('from .entitlements import active_node_ids, ensure_node_capacity','from .entitlements import active_node_ids, ensure_node_capacity, set_active_node')
s=s.replace('    active=set(active_node_ids(gateway.db_path,user.id))\n    for node in authorized_nodes:\n        node["plan_limited"] = bool(node.get("authorized") and str(node.get("node_id") or "") not in active)', '    preferred=[str(n.get("node_id") or "") for n in sorted(authorized_nodes,key=lambda n: float(n.get("last_seen") or 0),reverse=True) if n.get("authorized") and n.get("online")]\n    active=set(active_node_ids(gateway.db_path,user.id,preferred))\n    for node in authorized_nodes:\n        node_id=str(node.get("node_id") or "")\n        node["active"] = bool(node.get("authorized") and node_id in active)\n        node["plan_limited"] = bool(node.get("authorized") and node_id not in active)')
marker='''async def api_node_name(request: Request):\n'''
handler='''async def api_activate_node(request: Request):\n    user=_auth_user(request)\n    node_id=unquote(request.path_params["node_id"])\n    try:\n        active=set_active_node(gateway.db_path,user.id,node_id)\n        gateway.auth.audit(user.id,"node.activate",node_id,{"active_node_ids":active})\n        return JSONResponse({"ok":True,"active_node_ids":active,"billing":gateway.billing.summary(user.id)})\n    except (ValueError,PermissionError) as exc:\n        return JSONResponse({"error":str(exc)},status_code=400)\n\n\n'''
if 'async def api_activate_node' not in s:
    if marker not in s: raise SystemExit('webapp node name marker missing')
    s=s.replace(marker,handler+marker,1)
route='    Route("/api/nodes/{node_id}/activate", api_activate_node, methods=["POST"]),\n'
if route not in s:
    anchor='    Route("/api/nodes/{node_id}/name", api_node_name, methods=["PUT"]),\n'
    if anchor not in s: raise SystemExit('webapp route anchor missing')
    s=s.replace(anchor,anchor+route,1)
p.write_text(s,encoding='utf-8')

# dashboard runtime: plan-limited computers become switchable instead of upgrade-only
p=SRC/'web_core_runtime.py'; s=p.read_text(encoding='utf-8')
old='action=n.plan_limited?`<button class="btn primary" onclick="location.href=\\\'/billing\\\'">Upgrade</button>`:(authorized?'
new='action=n.plan_limited?`<button class="btn primary" onclick="activateNode(\\\'${encodeURIComponent(n.node_id)}\\\')">Activate</button>`:(authorized?'
if old not in s: raise SystemExit('core plan-limit action marker missing')
s=s.replace(old,new,1)
insert="\\nasync function activateNode(nodeId){try{await api('/api/nodes/'+nodeId+'/activate',{method:'POST'});toast('Computer activated');await refresh()}catch(e){toast(e.message)}}"
# insert escaped JS inside Python string after renderNodes function line
needle="\\nfunction applyNodeUpsert(node){"
if 'async function activateNode' not in s:
    if needle not in s: raise SystemExit('core applyNodeUpsert marker missing')
    s=s.replace(needle,insert+needle,1)
p.write_text(s,encoding='utf-8')

# Billing metric clarifies active vs connected.
p=SRC/'web_billing_runtime.py'; s=p.read_text(encoding='utf-8')
old="billingEl(\\'billingComputers\\').textContent=Number(s.nodes_used||0)+\\' / \\'+Number(s.node_limit||0);"
new="billingEl(\\'billingComputers\\').textContent=Number(s.nodes_used||0)+\\' / \\'+Number(s.node_limit||0)+(Number(s.nodes_connected||0)>Number(s.node_limit||0)?\\' active · \\'+Number(s.nodes_connected||0)+\\' connected\\':\\'\\');"
if old not in s: raise SystemExit('billing computers marker missing')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')

# Rewrite entitlement tests for active-computer semantics.
p=ROOT/'tests'/'test_billing_entitlements.py'; t=p.read_text(encoding='utf-8')
t=t.replace('from gpt_windows_connector.entitlements import ensure_ai_capacity, ensure_node_active, ensure_node_capacity, ensure_request_capacity, snapshot','from gpt_windows_connector.entitlements import active_node_ids, ensure_ai_capacity, ensure_node_active, ensure_node_capacity, ensure_request_capacity, set_active_node, snapshot')
t=t.replace('''    with pytest.raises(PermissionError): ensure_node_capacity(p,"u","n4")\n    with pytest.raises(PermissionError): ensure_ai_capacity(p,"u","c2")\n    ensure_node_active(p,"u","n1")''','''    ensure_node_capacity(p,"u","n4")\n    with pytest.raises(PermissionError): ensure_ai_capacity(p,"u","c2")\n    assert len(active_node_ids(p,"u")) == 3\n    ensure_node_active(p,"u",active_node_ids(p,"u")[0])''')
t=t.replace('''    with pytest.raises(PermissionError): ensure_node_active(p,"u","n3")\n    with sqlite3.connect(p) as db: assert db.execute("SELECT COUNT(*) FROM user_node_bindings").fetchone()[0]==4''','''    active=active_node_ids(p,"u")\n    inactive=next(n for n in ["n0","n1","n2","n3"] if n not in active)\n    with pytest.raises(PermissionError): ensure_node_active(p,"u",inactive)\n    set_active_node(p,"u",inactive)\n    ensure_node_active(p,"u",inactive)\n    assert inactive in active_node_ids(p,"u")\n    with sqlite3.connect(p) as db: assert db.execute("SELECT COUNT(*) FROM user_node_bindings").fetchone()[0]==4''')
# Add explicit Free migration/online preference regression
if 'test_free_prefers_online_computer_and_allows_manual_switch' not in t:
    t += '''\n\ndef test_free_prefers_online_computer_and_allows_manual_switch(tmp_path):\n    p=tmp_path/"db.sqlite"; schema(p)\n    now=time.time()\n    with sqlite3.connect(p) as db:\n        db.executemany("INSERT INTO user_node_bindings VALUES(?,?,?)",[("u","old-offline",now-100),("u","online",now-50),("u","other",now-10)])\n    assert active_node_ids(p,"u",["online"]) == ["online"]\n    assert snapshot(p,"u").nodes_used == 1\n    assert snapshot(p,"u").nodes_connected == 3\n    set_active_node(p,"u","other")\n    assert active_node_ids(p,"u",["online"]) == ["other"]\n    with pytest.raises(PermissionError): ensure_node_active(p,"u","online")\n    ensure_node_active(p,"u","other")\n'''
p.write_text(t,encoding='utf-8')

# Add UI contract regression test.
p=ROOT/'tests'/'test_active_computer_ui.py'
p.write_text('''from gpt_windows_connector.webapp import _dashboard_html\n\n\ndef test_computers_offer_activation_for_over_limit_bindings():\n    html=_dashboard_html()\n    assert "/api/nodes/" in html\n    assert "/activate" in html\n    assert "Computer activated" in html\n    assert "Activate</button>" in html\n''',encoding='utf-8')
print('active computer migration applied')
