from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "gpt_windows_connector"


def read(name: str) -> str:
    return (PKG / name).read_text(encoding="utf-8")


def write(name: str, text: str) -> None:
    (PKG / name).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing patch target: {label}")
    return text.replace(old, new, 1)


# 1) Persist pending access requests beside approved users.
ac = read("access_control.py")
needle = '''    def remove(self, user_id: str) -> bool:\n'''
insert = '''    def list_pending(self) -> list[dict[str, Any]]:\n        pending = self.load().get("pending", {})\n        if not isinstance(pending, dict):\n            return []\n        out: list[dict[str, Any]] = []\n        for user_id, record in pending.items():\n            if not isinstance(record, dict):\n                continue\n            out.append({"user_id": str(user_id), **record, "_pending": True})\n        return sorted(out, key=lambda item: float(item.get("requested_at") or 0), reverse=True)\n\n    def add_pending(self, actor: dict[str, Any]) -> dict[str, Any]:\n        user_id = str(actor.get("user_id") or actor.get("id") or "").strip()\n        if not user_id:\n            raise ValueError("user_id is required")\n        data = self.load()\n        pending = data.setdefault("pending", {})\n        now = time.time()\n        previous = pending.get(user_id) if isinstance(pending.get(user_id), dict) else {}\n        record = {\n            "email": str(actor.get("email") or previous.get("email") or ""),\n            "name": str(actor.get("name") or previous.get("name") or ""),\n            "requested_at": float(previous.get("requested_at") or now),\n            "updated_at": now,\n        }\n        pending[user_id] = record\n        self.save(data)\n        return {"user_id": user_id, **record, "_pending": True}\n\n    def remove_pending(self, user_id: str) -> bool:\n        data = self.load()\n        pending = data.setdefault("pending", {})\n        removed = pending.pop(str(user_id), None) is not None\n        if removed:\n            self.save(data)\n        return removed\n\n'''
ac = replace_once(ac, needle, insert + needle, "LocalAccessStore pending methods")
# Approval should always clear a stale pending request.
old = '''        users[user_id] = record\n        self.save(data)\n        return {"user_id": user_id, **record}\n'''
new = '''        users[user_id] = record\n        pending = data.setdefault("pending", {})\n        if isinstance(pending, dict):\n            pending.pop(user_id, None)\n        self.save(data)\n        return {"user_id": user_id, **record}\n'''
ac = replace_once(ac, old, new, "clear pending on approval")
write("access_control.py", ac)


# 2) Replace blocking approval dialog with a small bottom-right notification.
write("node_approval.py", r'''from __future__ import annotations

import os
import subprocess
import sys

from .i18n import tr


def notify_access_request(actor: dict[str, object]) -> None:
    """Show a non-blocking-style local toast; clicking opens Users & Permissions."""
    try:
        import tkinter as tk
    except Exception:
        return

    try:
        root = tk.Tk()
        root.title(tr("Lucas 访问请求", "Lucas Access Request"))
        root.resizable(False, False)
        root.attributes("-topmost", True)
        root.configure(bg="#ffffff")
        width, height = 390, 150
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{width}x{height}+{max(sw-width-24,0)}+{max(sh-height-72,0)}")
        display = str(actor.get("name") or actor.get("email") or actor.get("user_id") or tr("未知用户", "Unknown user"))
        email = str(actor.get("email") or "")
        frame = tk.Frame(root, bg="#ffffff", padx=18, pady=14)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=tr("Lucas 访问申请", "Lucas access request"), font=("Segoe UI", 11, "bold"), bg="#ffffff", fg="#1f1f1f").pack(anchor="w")
        tk.Label(frame, text=display, font=("Segoe UI", 10, "bold"), bg="#ffffff", fg="#1f1f1f").pack(anchor="w", pady=(7, 0))
        if email and email != display:
            tk.Label(frame, text=email, font=("Segoe UI", 8), bg="#ffffff", fg="#666666").pack(anchor="w")
        tk.Label(frame, text=tr("点击打开“用户与权限”进行批准和权限设置。", "Click to open Users & Permissions to approve and configure access."), font=("Segoe UI", 8), bg="#ffffff", fg="#666666").pack(anchor="w", pady=(5, 8))

        def open_settings() -> None:
            env = os.environ.copy()
            env["LUCAS_SETTINGS_PAGE"] = "用户与权限"
            try:
                subprocess.Popen([sys.executable, "-m", "gpt_windows_connector.node", "--configure"], env=env, close_fds=True)
            except Exception:
                pass
            root.destroy()

        tk.Button(frame, text=tr("打开用户与权限", "Open Users & Permissions"), command=open_settings, bg="#0f8ce9", fg="#ffffff", relief="flat", padx=12, pady=5).pack(anchor="e")
        root.after(15000, root.destroy)
        root.mainloop()
    except Exception:
        return
''')


# 3) Node: validate code, persist pending request, notify, return immediately.
node = read("node.py")
node = replace_once(node, 'from .node_approval import prompt_access_request as _prompt_access_request', 'from .node_approval import notify_access_request as _notify_access_request', "node approval import")
old = '''            access_attempts.pop(user_id, None)\n            decision = await asyncio.to_thread(_prompt_access_request, actor, node_roots)\n            choice = str(decision.get("decision") or "deny")\n            roots = clamp_roots([str(item) for item in decision.get("allowed_roots") or []], node_roots)\n            preset = normalize_preset(str(decision.get("preset") or "request_approval"))\n            security = preset_security(preset)\n            if choice not in {"once", "always"} or not roots:\n                log.info("Local access denied for user %s", user_id)\n                return {"authorized": False, "decision": "deny"}\n            grant = {"user_id": user_id, "email": str(actor.get("email") or ""), "name": str(actor.get("name") or ""), "preset": preset, "security": security, "allowed_roots": roots}\n            if choice == "once":\n                grant["grant_id"] = uuid.uuid4().hex\n                grant["expires_at"] = time.time() + 3600\n            if choice == "always":\n                saved = local_access.upsert(actor, preset, roots, security=security)\n                grant.update(saved)\n            else:\n                session_grants[user_id] = dict(grant)\n            log.info("Local access approved for user %s preset=%s mode=%s", user_id, preset, choice)\n            return {"authorized": True, "decision": choice, **grant}\n'''
new = '''            access_attempts.pop(user_id, None)\n            pending = local_access.add_pending(actor)\n            asyncio.create_task(asyncio.to_thread(_notify_access_request, actor))\n            log.info("Local access request pending approval for user %s", user_id)\n            return {"authorized": False, "pending": True, "decision": "pending", "user_id": user_id, "requested_at": pending.get("requested_at")}\n'''
node = replace_once(node, old, new, "non-blocking access request")
write("node.py", node)


# 4) Settings: deep-link to Users & Permissions, show pending users, approve/reject there,
# and keep Allowed Folders synchronized between File Access and Users & Permissions.
su = read("settings_ui.py")
old = '''def _load_last_page() -> str:\n    allowed = {"常规", "安全", "用户与权限", "文件访问", "网络", "规则", "任务记录", "日志", "系统访问"}\n    try:\n'''
new = '''def _load_last_page() -> str:\n    allowed = {"常规", "安全", "用户与权限", "文件访问", "网络", "规则", "任务记录", "日志", "系统访问"}\n    requested = str(os.environ.get("LUCAS_SETTINGS_PAGE") or "").strip()\n    if requested in allowed:\n        return requested\n    try:\n'''
su = replace_once(su, old, new, "settings deep link")
old = '''    def refresh_users(select_id=None):\n        nonlocal user_records\n        user_records=access_store.list_users(); user_list.delete(0,"end")\n'''
new = '''    def refresh_users(select_id=None):\n        nonlocal user_records\n        user_records=access_store.list_pending()+access_store.list_users(); user_list.delete(0,"end")\n'''
su = replace_once(su, old, new, "pending users in settings")
old = '''            user_list.insert("end",f"{label}   [{preset_value}]")\n'''
new = '''            status = "待批准" if record.get("_pending") else preset_value\n            user_list.insert("end",f"{label}   [{status}]")\n'''
su = replace_once(su, old, new, "pending label")
old = '''        user_roots.selection_clear(0,"end"); granted={str(Path(v).expanduser().resolve()) for v in (record.get("allowed_roots") or [])}\n        for idx,path in enumerate(roots):\n            try: resolved=str(Path(path).expanduser().resolve())\n            except Exception: resolved=path\n            if resolved in granted: user_roots.selection_set(idx)\n'''
new = '''        user_roots.selection_clear(0,"end"); granted={str(Path(v).expanduser().resolve()) for v in (record.get("allowed_roots") or [])}\n        for idx,path in enumerate(roots):\n            try: resolved=str(Path(path).expanduser().resolve())\n            except Exception: resolved=path\n            if record.get("_pending") or resolved in granted: user_roots.selection_set(idx)\n        if record.get("_pending"):\n            user_note.set("待批准申请：选择快捷权限和允许文件夹后点击“保存权限”即批准；点击“撤销访问”即拒绝。")\n'''
su = replace_once(su, old, new, "pending root defaults")
old = '''        access_store.upsert({"user_id":uid,"name":record.get("name"),"email":record.get("email")},preset,selected,security=security,enabled=True)\n        user_note.set("已保存。快捷权限和文件夹会在该用户下一次操作时立即生效。"); refresh_users(uid)\n'''
new = '''        was_pending=bool(record.get("_pending"))\n        access_store.upsert({"user_id":uid,"name":record.get("name"),"email":record.get("email")},preset,selected,security=security,enabled=True)\n        user_note.set("申请已批准。" if was_pending else "已保存。快捷权限和文件夹会在该用户下一次操作时立即生效。"); refresh_users(uid)\n'''
su = replace_once(su, old, new, "approve pending in settings")
old = '''        if not messagebox.askyesno("Lucas",f"撤销 {label} 对这台电脑的访问权限？\\n\\n撤销后，该用户必须重新在本机获得批准。"): return\n        access_store.remove(uid); user_note.set("已撤销访问。"); refresh_users()\n'''
new = '''        if record and record.get("_pending"):\n            if not messagebox.askyesno("Lucas",f"拒绝 {label} 的访问申请？"): return\n            access_store.remove_pending(uid); user_note.set("已拒绝访问申请。"); refresh_users(); return\n        if not messagebox.askyesno("Lucas",f"撤销 {label} 对这台电脑的访问权限？\\n\\n撤销后，该用户必须重新在本机获得批准。"): return\n        access_store.remove(uid); user_note.set("已撤销访问。"); refresh_users()\n'''
su = replace_once(su, old, new, "reject pending")
old = '''    def add_root():\n        p=filedialog.askdirectory(title="选择 Lucas 可以访问的文件夹")\n        if p and p not in roots_list.get(0,"end"): roots_list.insert("end",p)\n    def remove_root():\n        sel=roots_list.curselection()\n        if sel: roots_list.delete(sel[0])\n'''
new = '''    def add_root():\n        p=filedialog.askdirectory(title="选择 Lucas 可以访问的文件夹")\n        if p and p not in roots_list.get(0,"end"):\n            roots_list.insert("end",p)\n            if p not in roots: roots.append(p)\n            if p not in user_roots.get(0,"end"): user_roots.insert("end",p)\n    def remove_root():\n        sel=roots_list.curselection()\n        if sel:\n            value=str(roots_list.get(sel[0])); roots_list.delete(sel[0])\n            roots[:] = [r for r in roots if str(r) != value]\n            values=list(user_roots.get(0,"end"))\n            if value in values: user_roots.delete(values.index(value))\n            refresh_users(selected_user_id["value"] or None)\n'''
su = replace_once(su, old, new, "sync allowed folders")
write("settings_ui.py", su)


# 5) Web backend: persist pending node requests and include them in /api/nodes.
wa = read("webapp.py")
old = '''    CREATE TABLE IF NOT EXISTS dashboard_ai_metadata(\n        user_id TEXT NOT NULL, client_id TEXT NOT NULL, display_name TEXT, note TEXT, updated_at REAL NOT NULL,\n        PRIMARY KEY(user_id,client_id)\n    );\n'''
new = '''    CREATE TABLE IF NOT EXISTS dashboard_ai_metadata(\n        user_id TEXT NOT NULL, client_id TEXT NOT NULL, display_name TEXT, note TEXT, updated_at REAL NOT NULL,\n        PRIMARY KEY(user_id,client_id)\n    );\n    CREATE TABLE IF NOT EXISTS dashboard_pending_node_access(\n        user_id TEXT NOT NULL, node_id TEXT NOT NULL, node_name TEXT, requested_at REAL NOT NULL, updated_at REAL NOT NULL,\n        PRIMARY KEY(user_id,node_id)\n    );\n'''
wa = replace_once(wa, old, new, "pending dashboard schema")
old = '''    aliases = {r["node_id"]: r["display_name"] for r in rows if r["display_name"]}\n    for node in nodes:\n        node["display_name"] = aliases.get(node["node_id"]) or node.get("name") or node["node_id"]\n    return JSONResponse({"nodes": nodes})\n'''
new = '''    aliases = {r["node_id"]: r["display_name"] for r in rows if r["display_name"]}\n    authorized_ids = {str(node.get("node_id")) for node in nodes}\n    with _db() as db:\n        _ensure_dashboard_metadata_schema(db)\n        for node_id in authorized_ids:\n            db.execute("DELETE FROM dashboard_pending_node_access WHERE user_id=? AND node_id=?", (user.id,node_id))\n        pending_rows = db.execute("SELECT node_id,node_name,requested_at,updated_at FROM dashboard_pending_node_access WHERE user_id=? ORDER BY updated_at DESC", (user.id,)).fetchall()\n    for node in nodes:\n        node["display_name"] = aliases.get(node["node_id"]) or node.get("name") or node["node_id"]\n    for row in pending_rows:\n        node_id=str(row["node_id"])\n        if node_id in authorized_ids: continue\n        live=gateway.registry.nodes.get(node_id)\n        name=str(row["node_name"] or (live.name if live else node_id))\n        nodes.append({"node_id":node_id,"name":name,"display_name":aliases.get(node_id) or name,"pending":True,"online":bool(live),"preset":"request_approval","allowed_roots":[],"last_seen":live.last_seen if live else row["updated_at"],"requested_at":row["requested_at"]})\n    return JSONResponse({"nodes": nodes})\n'''
wa = replace_once(wa, old, new, "pending nodes in api")
old = '''        if isinstance(result, dict) and result.get("authorized"):\n            gateway.bindings.upsert(user.id, node_id)\n        gateway.auth.audit(user.id, "node.access_request", node_id, {"authorized": bool(isinstance(result, dict) and result.get("authorized"))})\n        return JSONResponse(result if isinstance(result, dict) else {"authorized": False})\n'''
new = '''        if isinstance(result, dict) and result.get("authorized"):\n            gateway.bindings.upsert(user.id, node_id)\n            with _db() as db:\n                _ensure_dashboard_metadata_schema(db); db.execute("DELETE FROM dashboard_pending_node_access WHERE user_id=? AND node_id=?", (user.id,node_id))\n        elif isinstance(result, dict) and result.get("pending"):\n            live=gateway.registry.nodes.get(node_id); node_name=live.name if live else node_id; now=time.time()\n            with _db() as db:\n                _ensure_dashboard_metadata_schema(db); db.execute("INSERT INTO dashboard_pending_node_access(user_id,node_id,node_name,requested_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id,node_id) DO UPDATE SET node_name=excluded.node_name,updated_at=excluded.updated_at", (user.id,node_id,node_name,float(result.get("requested_at") or now),now))\n        gateway.auth.audit(user.id, "node.access_request", node_id, {"authorized": bool(isinstance(result, dict) and result.get("authorized")), "pending": bool(isinstance(result, dict) and result.get("pending"))})\n        return JSONResponse(result if isinstance(result, dict) else {"authorized": False})\n'''
wa = replace_once(wa, old, new, "persist pending web request")
write("webapp.py", wa)


# 6) Realtime: when local settings approves a pending user, push node.upsert.
gw = read("gateway.py")
old = '''            elif message.get("type") == "access.sync":\n                _, removed = bindings.reconcile_node(node_id, [str(v) for v in message.get("authorized_user_ids") or []])\n                for user_id in removed:\n'''
new = '''            elif message.get("type") == "access.sync":\n                added, removed = bindings.reconcile_node(node_id, [str(v) for v in message.get("authorized_user_ids") or []])\n                for user_id in added:\n                    try:\n                        user = auth.get_user(user_id)\n                        visible = await registry.list(user)\n                        node_payload = next((item for item in visible if item.get("node_id") == node_id), None)\n                        if node_payload:\n                            await dashboard_events.publish(user_id, "node.upsert", {"node": node_payload})\n                    except Exception:\n                        log.exception("Could not publish approved node for user=%s node=%s", user_id, node_id)\n                for user_id in removed:\n'''
gw = replace_once(gw, old, new, "publish approved node")
write("gateway.py", gw)


# 7) Web UI: explicit Pending approval status and immediate refresh after request.
assets = read("web_assets.py")
old = '''function nodeRowHtml(n){return `<tr data-node-key="${encodeURIComponent(n.node_id)}"><td><b>${esc(n.display_name||n.name||n.node_id)}</b><div class="muted">${esc(n.node_id)}</div></td><td><span class="badge ${n.online?'online':'offline'}">${n.online?'Online':'Offline'}</span></td><td>${esc(accessMode(n))}</td><td class="path">${esc((n.allowed_roots||[]).join('\\n')||'—')}</td><td>${esc(timefmt(n.last_seen||n.updated_at))}</td><td><button class="btn secondary" onclick="openNodeModal('${encodeURIComponent(n.node_id)}')">View</button></td></tr>`}\n'''
new = '''function nodeRowHtml(n){const status=n.pending?'Pending approval':(n.online?'Online':'Offline'),badge=n.pending?'coming':(n.online?'online':'offline');return `<tr data-node-key="${encodeURIComponent(n.node_id)}"><td><b>${esc(n.display_name||n.name||n.node_id)}</b><div class="muted">${esc(n.node_id)}</div></td><td><span class="badge ${badge}">${esc(status)}</span></td><td>${n.pending?'Awaiting local approval':esc(accessMode(n))}</td><td class="path">${n.pending?'—':esc((n.allowed_roots||[]).join('\\n')||'—')}</td><td>${esc(timefmt(n.last_seen||n.updated_at))}</td><td>${n.pending?'':`<button class="btn secondary" onclick="openNodeModal('${encodeURIComponent(n.node_id)}')">View</button>`}</td></tr>`}\n'''
assets = replace_once(assets, old, new, "pending node row")
old = '''async function requestNodeAccess(){const node_id=connectNodeId.value.trim(),connection_code=connectCode.value.trim();if(!node_id){toast('Node ID is required');return}if(!/^\\d{8}$/.test(connection_code)){toast('Enter the 8-digit Connection Code');return}connectResult.textContent='Waiting for approval on the target computer…';connectResult.classList.remove('hidden');try{const d=await api('/api/nodes/request-access',{method:'POST',body:JSON.stringify({node_id,connection_code})});if(d.authorized){connectResult.textContent=d.decision==='always'?'Access approved and saved on the target computer.':'Access approved for this session.';await refresh()}else{connectResult.textContent=d.error==='invalid connection code'?'Connection Code is incorrect.':'Access was not approved on the target computer.'}}catch(e){connectResult.textContent=e.message}}\n'''
new = '''async function requestNodeAccess(){const node_id=connectNodeId.value.trim(),connection_code=connectCode.value.trim();if(!node_id){toast('Node ID is required');return}if(!/^\\d{8}$/.test(connection_code)){toast('Enter the 8-digit Connection Code');return}connectResult.textContent='Sending access request…';connectResult.classList.remove('hidden');try{const d=await api('/api/nodes/request-access',{method:'POST',body:JSON.stringify({node_id,connection_code})});if(d.authorized){connectResult.textContent='Access approved on the target computer.';await refresh()}else if(d.pending){connectResult.textContent='Access request sent. Waiting for local approval on the target computer.';await refresh()}else{connectResult.textContent=d.error==='invalid connection code'?'Connection Code is incorrect.':'Access request was not accepted.'}}catch(e){connectResult.textContent=e.message}}\n'''
assets = replace_once(assets, old, new, "pending request UI")
write("web_assets.py", assets)

print("pending access flow patched")
