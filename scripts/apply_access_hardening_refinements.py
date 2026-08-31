from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected block not found in {path}: {old[:100]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/gpt_windows_connector/gateway.py",
    '''                CREATE TABLE IF NOT EXISTS nodes (\n                    node_id TEXT PRIMARY KEY,\n                    owner_user_id TEXT NOT NULL,\n                    name TEXT NOT NULL,\n                    token TEXT NOT NULL,\n                    updated_at REAL NOT NULL\n                )\n''',
    '''                CREATE TABLE IF NOT EXISTS nodes (\n                    node_id TEXT PRIMARY KEY,\n                    name TEXT NOT NULL,\n                    token TEXT NOT NULL,\n                    updated_at REAL NOT NULL,\n                    allowed_roots TEXT NOT NULL DEFAULT '[]'\n                )\n''',
)

replace_once(
    "src/gpt_windows_connector/node.py",
    '        access_file_mtime = ACCESS_FILE.stat().st_mtime if ACCESS_FILE.exists() else 0.0\n\n        def effective_access',
    '        access_file_mtime = ACCESS_FILE.stat().st_mtime if ACCESS_FILE.exists() else 0.0\n        access_attempts: dict[str, list[float]] = {}\n\n        def effective_access',
)
replace_once(
    "src/gpt_windows_connector/node.py",
    '''            current = effective_access(actor)\n            if current:\n                return {"authorized": True, **current}\n            if not supplied_connection_code or not secrets.compare_digest(connection_code, supplied_connection_code.strip()):\n                log.warning("Invalid connection code for access request user=%s", user_id)\n                return {"authorized": False, "error": "invalid connection code"}\n            decision = await asyncio.to_thread(_prompt_access_request, actor, node_roots)\n''',
    '''            current = effective_access(actor)\n            if current:\n                return {"authorized": True, **current}\n            now = time.time()\n            attempts = [stamp for stamp in access_attempts.get(user_id, []) if now - stamp < 60]\n            access_attempts[user_id] = attempts\n            if len(attempts) >= 5:\n                log.warning("Local connection-code rate limit user=%s", user_id)\n                return {"authorized": False, "error": "too many connection attempts"}\n            if not supplied_connection_code or not secrets.compare_digest(connection_code, supplied_connection_code.strip()):\n                attempts.append(now)\n                access_attempts[user_id] = attempts\n                log.warning("Invalid connection code for access request user=%s", user_id)\n                return {"authorized": False, "error": "invalid connection code"}\n            access_attempts.pop(user_id, None)\n            decision = await asyncio.to_thread(_prompt_access_request, actor, node_roots)\n''',
)

replace_once(
    "src/gpt_windows_connector/settings_ui.py",
    '''    def build_connection_code(p):\n        f=tk.Frame(p,bg=C["card"]); tk.Label(f,textvariable=connection_code,font=(FONT,14,"bold"),fg=C["blue"],bg=C["card"]).pack(side="left"); button(f,"重新生成",lambda: connection_code.set(f"{secrets.randbelow(100_000_000):08d}")).pack(side="left",padx=(10,0)); return f\n''',
    '''    def regenerate_connection_code():\n        new_code=f"{secrets.randbelow(100_000_000):08d}"\n        connection_code.set(new_code)\n        latest=dict(existing); latest["connection_code"]=new_code\n        _save_config(latest); _restart_node_for_apply()\n    def build_connection_code(p):\n        f=tk.Frame(p,bg=C["card"]); tk.Label(f,textvariable=connection_code,font=(FONT,14,"bold"),fg=C["blue"],bg=C["card"]).pack(side="left"); button(f,"重新生成",regenerate_connection_code).pack(side="left",padx=(10,0)); return f\n''',
)

print("Lucas access hardening refinements applied")
