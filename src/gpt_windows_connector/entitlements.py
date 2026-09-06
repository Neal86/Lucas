from __future__ import annotations

import calendar
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    cancel_at_period_end: bool; bonus_requests: int
    @property
    def can_buy_expansion(self) -> bool: return self.plan == "pro_plus" and self.status in ACTIVE_STATUSES
    def as_dict(self) -> dict[str, Any]:
        return {"plan":self.plan,"plan_name":self.plan_name,"status":self.status,"expansion_quantity":self.expansion_quantity,"request_limit":self.request_limit,"node_limit":self.node_limit,"ai_account_limit":self.ai_account_limit,"requests_used":self.requests_used,"nodes_used":self.nodes_used,"ai_accounts_used":self.ai_accounts_used,"period_start":self.period_start,"period_end":self.period_end,"renewal_at":self.renewal_at,"cancel_at_period_end":self.cancel_at_period_end,"bonus_requests":self.bonus_requests,"can_buy_expansion":self.can_buy_expansion,"request_remaining":max(0,self.request_limit-self.requests_used),"node_remaining":max(0,self.node_limit-self.nodes_used),"ai_account_remaining":max(0,self.ai_account_limit-self.ai_accounts_used)}

def _connect(db_path: Path) -> sqlite3.Connection:
    db=sqlite3.connect(db_path,timeout=30); db.row_factory=sqlite3.Row; return db

def _free_period(now: float) -> tuple[float,float]:
    tm=time.gmtime(now); start=calendar.timegm((tm.tm_year,tm.tm_mon,1,0,0,0,0,0,0))
    end=calendar.timegm((tm.tm_year+1,1,1,0,0,0,0,0,0)) if tm.tm_mon==12 else calendar.timegm((tm.tm_year,tm.tm_mon+1,1,0,0,0,0,0,0))
    return float(start),float(end)

def snapshot(db_path: Path,user_id: str,now: float|None=None) -> Entitlements:
    now=float(now or time.time())
    with _connect(db_path) as db:
        row=db.execute("SELECT * FROM subscriptions WHERE user_id=?",(user_id,)).fetchone()
        status=str(row["status"] if row and "status" in row.keys() else "inactive")
        raw=str(row["plan"] if row and "plan" in row.keys() else "free")
        plan=raw if raw in PLANS and status in ACTIVE_STATUSES else "free"
        expansion=int((row["expansion_quantity"] if row and "expansion_quantity" in row.keys() else 0) or 0) if plan=="pro_plus" else 0
        bonus=int((row["bonus_requests"] if row and "bonus_requests" in row.keys() else 0) or 0)
        pstart=float((row["current_period_start"] if row and "current_period_start" in row.keys() else 0) or 0); pend=float((row["current_period_end"] if row and "current_period_end" in row.keys() else 0) or 0)
        if plan=="free" or pstart<=0 or pend<=pstart: pstart,pend=_free_period(now)
        req=int(db.execute("SELECT COUNT(*) FROM task_steps WHERE owner_id=? AND started_at>=? AND started_at<?",(user_id,pstart,pend)).fetchone()[0])
        nodes=int(db.execute("SELECT COUNT(*) FROM user_node_bindings WHERE user_id=?",(user_id,)).fetchone()[0])
        ai=int(db.execute("SELECT COUNT(*) FROM oauth_client_users WHERE user_id=?",(user_id,)).fetchone()[0])
        cancel=bool((row["cancel_at_period_end"] if row and "cancel_at_period_end" in row.keys() else 0) or 0)
    base=PLANS[plan]
    return Entitlements(plan,str(base["name"]),status if plan!="free" else "free",expansion,int(base["requests"])+expansion*int(EXPANSION["requests"])+bonus,int(base["nodes"])+expansion*int(EXPANSION["nodes"]),int(base["ai_accounts"])+expansion*int(EXPANSION["ai_accounts"]),req,nodes,ai,pstart,pend,pend if plan!="free" else None,cancel,bonus)

def ensure_request_capacity(db_path: Path,user_id: str) -> Entitlements:
    e=snapshot(db_path,user_id)
    if e.requests_used>=e.request_limit: raise PermissionError(f"Monthly Request limit reached ({e.requests_used}/{e.request_limit}). {'Add an Expansion Pack' if e.can_buy_expansion else 'Upgrade your plan'} at /billing.")
    return e

def ensure_node_capacity(db_path: Path,user_id: str,node_id: str) -> Entitlements:
    e=snapshot(db_path,user_id)
    with _connect(db_path) as db: exists=db.execute("SELECT 1 FROM user_node_bindings WHERE user_id=? AND node_id=?",(user_id,node_id)).fetchone()
    if not exists and e.nodes_used>=e.node_limit: raise PermissionError(f"Computer limit reached ({e.nodes_used}/{e.node_limit}). {'Add an Expansion Pack' if e.can_buy_expansion else 'Upgrade your plan'} at /billing.")
    return e

def ensure_ai_capacity(db_path: Path,user_id: str,client_id: str) -> Entitlements:
    e=snapshot(db_path,user_id)
    with _connect(db_path) as db: exists=db.execute("SELECT 1 FROM oauth_client_users WHERE user_id=? AND client_id=?",(user_id,client_id)).fetchone()
    if not exists and e.ai_accounts_used>=e.ai_account_limit: raise PermissionError(f"AI account limit reached ({e.ai_accounts_used}/{e.ai_account_limit}). {'Add an Expansion Pack' if e.can_buy_expansion else 'Upgrade to Pro+'} at /billing.")
    return e
