from pathlib import Path
import re

TASK_MODULE = r'''from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


class TaskRunStore:
    """SQLite-backed Lucas task/subtask timing store."""

    def __init__(self, path: Path, idle_seconds: float = 300.0) -> None:
        self.path = Path(path)
        self.idle_seconds = float(idle_seconds)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS task_runs (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, node_id TEXT NOT NULL,
                context_key TEXT NOT NULL, title TEXT NOT NULL, started_at REAL NOT NULL,
                last_activity_at REAL NOT NULL, ended_at REAL,
                success_count INTEGER NOT NULL DEFAULT 0, error_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_task_runs_owner_started ON task_runs(owner_id, started_at DESC);
            CREATE INDEX IF NOT EXISTS idx_task_runs_active ON task_runs(owner_id,node_id,context_key,last_activity_at DESC);
            CREATE TABLE IF NOT EXISTS task_steps (
                id TEXT PRIMARY KEY, task_run_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                node_id TEXT NOT NULL, action TEXT NOT NULL, target TEXT, status TEXT NOT NULL,
                started_at REAL NOT NULL, ended_at REAL NOT NULL, duration_ms INTEGER NOT NULL,
                details TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_task_steps_run_started ON task_steps(task_run_id, started_at ASC);
            """)

    @staticmethod
    def _title(action: str, target: str | None) -> str:
        clean = str(target or "").strip()
        if clean:
            try: name = Path(clean).name
            except Exception: name = clean
            if name: return f"{action} · {name}"
        return action or "Lucas task"

    def record_operation(self, *, owner_id: str, node_id: str, action: str,
                         target: str | None, started_at: float, ended_at: float,
                         status: str, details: dict[str, Any] | None = None,
                         context_key: str | None = None) -> str:
        owner_id=str(owner_id or "local"); node_id=str(node_id or "unknown")
        action=str(action or "operation"); target=str(target or "") or None
        context_key=str(context_key or target or "default")
        started_at=float(started_at); ended_at=max(started_at,float(ended_at))
        duration_ms=max(0,round((ended_at-started_at)*1000))
        with self._connect() as db:
            row=db.execute("SELECT * FROM task_runs WHERE owner_id=? AND node_id=? AND context_key=? ORDER BY last_activity_at DESC LIMIT 1",(owner_id,node_id,context_key)).fetchone()
            if row and ended_at-float(row["last_activity_at"]) <= self.idle_seconds:
                run_id=str(row["id"])
            else:
                run_id=uuid.uuid4().hex
                db.execute("INSERT INTO task_runs(id,owner_id,node_id,context_key,title,started_at,last_activity_at,ended_at) VALUES(?,?,?,?,?,?,?,?)",(run_id,owner_id,node_id,context_key,self._title(action,target),started_at,ended_at,ended_at))
            success=status=="success"
            db.execute("UPDATE task_runs SET last_activity_at=?,ended_at=?,success_count=success_count+?,error_count=error_count+? WHERE id=?",(ended_at,ended_at,1 if success else 0,0 if success else 1,run_id))
            db.execute("INSERT INTO task_steps(id,task_run_id,owner_id,node_id,action,target,status,started_at,ended_at,duration_ms,details) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(uuid.uuid4().hex,run_id,owner_id,node_id,action,target,status,started_at,ended_at,duration_ms,json.dumps(details or {},ensure_ascii=False)))
        return run_id

    def list_runs(self, owner_id: str, *, node_id: str | None=None, limit: int=100) -> list[dict[str,Any]]:
        owner_id=str(owner_id or "local"); limit=max(1,min(int(limit),500))
        where="owner_id=?"; params:list[Any]=[owner_id]
        if node_id: where+=" AND node_id=?"; params.append(str(node_id))
        params.append(limit)
        with self._connect() as db:
            rows=db.execute(f"SELECT * FROM task_runs WHERE {where} ORDER BY started_at DESC LIMIT ?",params).fetchall()
            out=[]; now=time.time()
            for row in rows:
                item=dict(row); last=float(item["last_activity_at"])
                item["status"]="running" if now-last <= self.idle_seconds else ("failed" if int(item["error_count"]) and not int(item["success_count"]) else "completed")
                end=now if item["status"]=="running" else float(item["ended_at"] or last)
                item["duration_ms"]=max(0,round((end-float(item["started_at"]))*1000))
                steps=[]
                for step in db.execute("SELECT * FROM task_steps WHERE task_run_id=? ORDER BY started_at ASC",(item["id"],)).fetchall():
                    sub=dict(step)
                    try: sub["details"]=json.loads(sub.get("details") or "{}")
                    except Exception: sub["details"]={}
                    steps.append(sub)
                item["steps"]=steps; out.append(item)
        return out
'''
Path('src/gpt_windows_connector/task_runs.py').write_text(TASK_MODULE,encoding='utf-8')

# gateway
p=Path('src/gpt_windows_connector/gateway.py'); s=p.read_text(encoding='utf-8')
anchor='from .registration_security import RegistrationSecurity, email_verification_enabled, send_verification_email\n'
if 'from .task_runs import TaskRunStore' not in s: s=s.replace(anchor,anchor+'from .task_runs import TaskRunStore\n',1)
anchor='registration_security = RegistrationSecurity(db_path)\n'
if 'task_runs = TaskRunStore(db_path)' not in s: s=s.replace(anchor,anchor+'task_runs = TaskRunStore(db_path)\n',1)
old='''    started = time.monotonic()\n    try:\n        result = await registry.rpc(node_id, user.id, method, payload)\n    except Exception as exc:\n        duration = time.monotonic() - started\n        auth.record_operation(user.id, False, duration)\n        auth.audit(user.id, method, resolved_workspace, {"node_id": node_id, "status": "failed", "duration_ms": round(duration * 1000), "error_type": type(exc).__name__})\n        raise\n    duration = time.monotonic() - started\n    auth.record_operation(user.id, True, duration)\n    auth.audit(user.id, method, resolved_workspace, {"node_id": node_id, "status": "success", "duration_ms": round(duration * 1000)})\n    return result'''
new='''    wall_started = time.time()\n    started = time.monotonic()\n    try:\n        result = await registry.rpc(node_id, user.id, method, payload)\n    except Exception as exc:\n        duration = time.monotonic() - started; wall_ended = time.time()\n        auth.record_operation(user.id, False, duration)\n        auth.audit(user.id, method, resolved_workspace, {"node_id": node_id, "status": "failed", "duration_ms": round(duration * 1000), "error_type": type(exc).__name__})\n        task_runs.record_operation(owner_id=user.id,node_id=node_id,action=method,target=resolved_workspace,started_at=wall_started,ended_at=wall_ended,status="failed",details={"error_type":type(exc).__name__},context_key=resolved_workspace)\n        raise\n    duration = time.monotonic() - started; wall_ended = time.time()\n    auth.record_operation(user.id, True, duration)\n    auth.audit(user.id, method, resolved_workspace, {"node_id": node_id, "status": "success", "duration_ms": round(duration * 1000)})\n    task_runs.record_operation(owner_id=user.id,node_id=node_id,action=method,target=resolved_workspace,started_at=wall_started,ended_at=wall_ended,status="success",context_key=resolved_workspace)\n    return result'''
if 'task_runs.record_operation' not in s:
    if old not in s: raise SystemExit('gateway timing block missing')
    s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')

# node
p=Path('src/gpt_windows_connector/node.py'); s=p.read_text(encoding='utf-8')
anchor='from .settings_ui import configure_gui as _configure_gui\n'
if 'from .task_runs import TaskRunStore' not in s: s=s.replace(anchor,anchor+'from .task_runs import TaskRunStore\n',1)
anchor='STATUS_FILE = CONFIG_DIR / "node-status.json"\n'
if 'TASK_RUNS_FILE' not in s: s=s.replace(anchor,anchor+'TASK_RUNS_FILE = CONFIG_DIR / "task-runs.db"\nlocal_task_runs = TaskRunStore(TASK_RUNS_FILE)\n',1)
old='''        async def execute_request(request_id: object, method: str, params: dict) -> None:\n            try:\n                result = await executor.call(method, params)\n                response = {"type": "response", "id": request_id, "ok": True, "result": result}\n            except asyncio.CancelledError:\n                raise\n            except Exception as exc:\n                log.exception("Execution failed: %s", method)\n                response = {"type": "response", "id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}\n            try:\n                await send_json(response)\n            except Exception:\n                log.exception("Failed sending response for %s", method)'''
new='''        async def execute_request(request_id: object, method: str, params: dict) -> None:\n            wall_started=time.time(); status="success"; error_type=None\n            try:\n                result = await executor.call(method, params)\n                response = {"type": "response", "id": request_id, "ok": True, "result": result}\n            except asyncio.CancelledError:\n                raise\n            except Exception as exc:\n                status="failed"; error_type=type(exc).__name__\n                log.exception("Execution failed: %s", method)\n                response = {"type": "response", "id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}\n            wall_ended=time.time()\n            try:\n                workspace=str(params.get("workspace") or "")\n                local_task_runs.record_operation(owner_id="local",node_id=settings.node_id,action=method,target=workspace or None,started_at=wall_started,ended_at=wall_ended,status=status,details={"error_type":error_type} if error_type else {},context_key=workspace or "default")\n            except Exception:\n                log.exception("Could not record local Task Run")\n            try:\n                await send_json(response)\n            except Exception:\n                log.exception("Failed sending response for %s", method)'''
if 'local_task_runs.record_operation' not in s:
    if old not in s: raise SystemExit('node execute block missing')
    s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')

# webapp
p=Path('src/gpt_windows_connector/webapp.py'); s=p.read_text(encoding='utf-8')
if 'async def api_task_runs' not in s:
    marker='\nasync def api_logs(request: Request):\n'
    code='''\nasync def api_task_runs(request: Request):\n    user = _auth_user(request)\n    limit = max(1, min(int(request.query_params.get("limit", "100")), 500))\n    node_id = request.query_params.get("node_id", "").strip() or None\n    return JSONResponse({"runs": gateway.task_runs.list_runs(user.id, node_id=node_id, limit=limit)})\n\n'''
    if marker not in s: raise SystemExit('api_logs marker missing')
    s=s.replace(marker,'\n'+code+'async def api_logs(request: Request):\n',1)
nav='<button class="nav" data-view="logs" onclick="view(\'logs\',this)">Activity Logs</button>'
if 'data-view="tasks"' not in s:
    s=s.replace(nav,'<button class="nav" data-view="tasks" onclick="view(\'tasks\',this)">Task Runs</button>'+nav,1)
logs='<div id="logs" class="view hidden"><div class="top"><div><h2>Activity Logs</h2>'
if 'id="tasks" class="view hidden"' not in s:
    task='<div id="tasks" class="view hidden"><div class="top"><div><h2>Task Runs</h2><p class="muted">Task and subtask execution time measured by Lucas MCP.</p></div><button class="btn secondary" onclick="loadTaskRuns()">Refresh</button></div><div id="taskRunSummary" class="grid" style="margin-bottom:16px"></div><div id="taskRunTable"></div></div>'
    s=s.replace(logs,task+logs,1)
if 'function loadTaskRuns()' not in s:
    marker='function renderRecent(logs){'
    js='''function durationfmt(ms){ms=Math.max(0,Number(ms)||0);const sec=Math.floor(ms/1000),h=Math.floor(sec/3600),m=Math.floor((sec%3600)/60),ss=sec%60;return h?`${h}h ${m}m ${ss}s`:m?`${m}m ${ss}s`:`${ss}s`}\nfunction taskStatusBadge(s){return `<span class="badge ${s==='running'?'online':s==='failed'?'offline':'coming'}">${esc(s)}</span>`}\nasync function loadTaskRuns(){const d=await api('/api/task-runs?limit=100'),runs=d.runs||[];const total=runs.reduce((a,r)=>a+(Number(r.duration_ms)||0),0),steps=runs.reduce((a,r)=>a+(r.steps||[]).length,0);taskRunSummary.innerHTML=`<div class="card"><div class="muted">Task runs</div><div class="metric">${runs.length}</div></div><div class="card"><div class="muted">Subtasks</div><div class="metric">${steps}</div></div><div class="card"><div class="muted">Recorded time</div><div class="metric" style="font-size:22px">${durationfmt(total)}</div></div>`;taskRunTable.innerHTML=runs.length?runs.map(r=>`<div class="card" style="margin-bottom:12px"><div style="display:flex;justify-content:space-between;gap:12px"><div><b>${esc(r.title)}</b><div class="muted">${esc(r.node_id)} · ${esc(timefmt(r.started_at))}</div></div><div style="text-align:right">${taskStatusBadge(r.status)}<div style="margin-top:6px;font-weight:700">${esc(durationfmt(r.duration_ms))}</div></div></div><table class="table" style="margin-top:12px"><tbody>${(r.steps||[]).map(x=>`<tr><td style="width:35%"><b>${esc(x.action)}</b></td><td>${esc(x.status)}</td><td style="text-align:right">${esc(durationfmt(x.duration_ms))}</td></tr>`).join('')}</tbody></table></div>`).join(''):'<div class="card empty">No Task Runs recorded yet.</div>'}\n'''
    if marker not in s: raise SystemExit('renderRecent marker missing')
    s=s.replace(marker,js+marker,1)
# view() implementation has loadLogs condition; inject adjacent.
s=s.replace("if(name==='logs')loadLogs();", "if(name==='tasks')loadTaskRuns();if(name==='logs')loadLogs();",1) if "if(name==='tasks')loadTaskRuns()" not in s else s
route='Route("/api/logs", api_logs, methods=["GET"]),'
if 'Route("/api/task-runs"' not in s: s=s.replace(route,'Route("/api/task-runs", api_task_runs, methods=["GET"]),\n    '+route,1)
p.write_text(s,encoding='utf-8')

# settings UI
p=Path('src/gpt_windows_connector/settings_ui.py'); s=p.read_text(encoding='utf-8')
if 'from .task_runs import TaskRunStore' not in s: s=s.replace('from typing import Any\n','from typing import Any\n\nfrom .task_runs import TaskRunStore\n',1)
if 'TASK_RUNS_FILE' not in s: s=s.replace('UI_STATE_FILE = CONFIG_DIR / "settings-ui-state.json"\n','UI_STATE_FILE = CONFIG_DIR / "settings-ui-state.json"\nTASK_RUNS_FILE = CONFIG_DIR / "task-runs.db"\n',1)
s=s.replace('{"常规", "安全", "文件访问", "网络", "规则", "系统访问"}','{"常规", "安全", "文件访问", "网络", "规则", "任务记录", "系统访问"}',1)
# Discover exact system page line and inject before it.
if 'pages["任务记录"]' not in s:
    m=re.search(r'(?m)^    system_wrapper,system_body=scroll_page\(\); pages\["系统访问"\]=system_wrapper\s*$',s)
    if not m: raise SystemExit('settings system page line missing')
    task='''    tasks_wrapper,tasks_body=scroll_page(); pages["任务记录"]=tasks_wrapper\n    section(tasks_body,"任务记录")\n    task_card=card(tasks_body)\n    tk.Label(task_card,text="记录本机通过 Lucas 执行的大任务与小任务耗时。5 分钟无新操作后自动结束一个大任务。",font=(FONT,9),fg=C["muted"],bg=C["card"],wraplength=650,justify="left").pack(anchor="w",padx=18,pady=(14,10))\n    task_list=tk.Frame(task_card,bg=C["card"]); task_list.pack(fill="both",expand=True,padx=18,pady=(0,14))\n    def _duration_text(ms):\n        sec=max(0,int((ms or 0)/1000)); h,rem=divmod(sec,3600); m,s=divmod(rem,60)\n        return f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s")\n    def refresh_local_tasks():\n        for child in task_list.winfo_children(): child.destroy()\n        try: runs=TaskRunStore(TASK_RUNS_FILE).list_runs("local",node_id=node_id.get().strip() or None,limit=100)\n        except Exception as exc:\n            tk.Label(task_list,text=f"无法读取任务记录：{exc}",font=(FONT,9),fg=C["red"],bg=C["card"]).pack(anchor="w",pady=8); return\n        if not runs:\n            tk.Label(task_list,text="还没有任务记录。",font=(FONT,9),fg=C["muted"],bg=C["card"]).pack(anchor="w",pady=8); return\n        for run in runs:\n            box=tk.Frame(task_list,bg=C["control"],highlightthickness=1,highlightbackground=C["line"]); box.pack(fill="x",pady=(0,8))\n            head=tk.Frame(box,bg=C["control"]); head.pack(fill="x",padx=12,pady=(10,6))\n            tk.Label(head,text=str(run.get("title") or "Lucas task"),font=(FONT,9,"bold"),fg=C["text"],bg=C["control"]).pack(side="left")\n            tk.Label(head,text=f"{run.get('status','')} · {_duration_text(run.get('duration_ms'))}",font=(FONT,9),fg=C["muted"],bg=C["control"]).pack(side="right")\n            for step in run.get("steps",[])[:20]:\n                row=tk.Frame(box,bg=C["control"]); row.pack(fill="x",padx=18,pady=2)\n                tk.Label(row,text=str(step.get("action") or "operation"),font=(FONT,8),fg=C["text"],bg=C["control"]).pack(side="left")\n                tk.Label(row,text=_duration_text(step.get("duration_ms")),font=(FONT,8),fg=C["muted"],bg=C["control"]).pack(side="right")\n    normal_button(task_card,"刷新",refresh_local_tasks).pack(anchor="e",padx=18,pady=(0,14))\n    refresh_local_tasks()\n\n'''
    s=s[:m.start()]+task+s[m.start():]
# Nav names are generated from a list near bottom; support exact style variants.
for old,new in [
    ('["常规", "安全", "文件访问", "网络", "规则", "系统访问"]','["常规", "安全", "文件访问", "网络", "规则", "任务记录", "系统访问"]'),
    ('["常规","安全","文件访问","网络","规则","系统访问"]','["常规","安全","文件访问","网络","规则","任务记录","系统访问"]')]:
    if old in s: s=s.replace(old,new,1)
# Add page description if dict is present; otherwise show_page still works using fallback title.
if '"任务记录":"查看本机 Lucas 大任务与小任务执行时间。"' not in s:
    s=s.replace('"规则":"设置自定义规则与行为约束。",','"规则":"设置自定义规则与行为约束。","任务记录":"查看本机 Lucas 大任务与小任务执行时间。",',1)
p.write_text(s,encoding='utf-8')

# version bump
p=Path('pyproject.toml'); s=p.read_text(encoding='utf-8')
m=re.search(r'(?m)^version = "(\d+)\.(\d+)\.(\d+)"$',s)
if not m: raise SystemExit('version missing')
a,b,c=map(int,m.groups()); nv=f'{a}.{b}.{c+1}'
s=s[:m.start()]+f'version = "{nv}"'+s[m.end():]; p.write_text(s,encoding='utf-8')
print('Task Runs implemented:',nv)
