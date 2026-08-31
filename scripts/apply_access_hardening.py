from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected block not found in {path}: {old[:80]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) Enforce Node policy as a hard ceiling over per-user policy.
replace_once(
    "src/gpt_windows_connector/access_control.py",
    "from typing import Any\n",
    "from typing import Any\n\n\n_DECISION_RANK = {\"allow\": 0, \"ask\": 1, \"always_ask\": 2, \"block\": 3}\n\n\ndef _stricter_decision(a: object, b: object, default: str = \"ask\") -> str:\n    left = str(a or default).lower()\n    right = str(b or default).lower()\n    if left not in _DECISION_RANK:\n        left = default\n    if right not in _DECISION_RANK:\n        right = default\n    return left if _DECISION_RANK[left] >= _DECISION_RANK[right] else right\n\n\ndef intersect_security(node_security: dict[str, Any] | None, user_security: dict[str, Any] | None) -> dict[str, Any]:\n    \"\"\"Return effective security where a user can only narrow Node-wide permissions.\"\"\"\n    from .security import DEFAULT_SECURITY\n\n    node = {**DEFAULT_SECURITY, **(node_security or {})}\n    user = {**DEFAULT_SECURITY, **(user_security or {})}\n    node_policy = {**DEFAULT_SECURITY[\"approval_policy\"], **dict(node.get(\"approval_policy\") or {})}\n    user_policy = {**DEFAULT_SECURITY[\"approval_policy\"], **dict(user.get(\"approval_policy\") or {})}\n    effective_policy = {\n        key: _stricter_decision(node_policy.get(key), user_policy.get(key), DEFAULT_SECURITY[\"approval_policy\"].get(key, \"ask\"))\n        for key in set(node_policy) | set(user_policy)\n    }\n\n    node_domains = [str(v).strip().lower() for v in node.get(\"allowed_domains\") or [] if str(v).strip()]\n    user_domains = [str(v).strip().lower() for v in user.get(\"allowed_domains\") or [] if str(v).strip()]\n    if node_domains and user_domains:\n        effective_domains = [v for v in user_domains if v in set(node_domains)]\n    else:\n        effective_domains = node_domains or user_domains\n\n    return {\n        **node,\n        \"approval_policy\": effective_policy,\n        \"remember_approvals\": bool(node.get(\"remember_approvals\", True)) and bool(user.get(\"remember_approvals\", True)),\n        \"network_external\": _stricter_decision(node.get(\"network_external\"), user.get(\"network_external\")),\n        \"network_lan\": _stricter_decision(node.get(\"network_lan\"), user.get(\"network_lan\")),\n        \"allowed_domains\": effective_domains,\n        \"block_silent_network\": bool(node.get(\"block_silent_network\", True)) or bool(user.get(\"block_silent_network\", True)),\n        \"show_rule_summary\": bool(node.get(\"show_rule_summary\", True)) or bool(user.get(\"show_rule_summary\", True)),\n        \"rules_text\": str(node.get(\"rules_text\") or DEFAULT_SECURITY[\"rules_text\"]),\n    }\n",
)

# 2) New installs use an opaque random Node ID instead of machine/MAC-derived IDs.
replace_once(
    "src/gpt_windows_connector/node.py",
    'from .access_control import LocalAccessStore, clamp_roots, normalize_preset, preset_security\n',
    'from .access_control import LocalAccessStore, clamp_roots, intersect_security, normalize_preset, preset_security\n',
)
replace_once(
    "src/gpt_windows_connector/node.py",
    'def _default_node_id() -> str:\n    machine = os.environ.get("COMPUTERNAME") or socket.gethostname() or "windows-node"\n    return f"{machine}-{uuid.getnode():012x}".lower()\n',
    'def _default_node_id() -> str:\n    return f"lucas-{uuid.uuid4().hex}"\n',
)
replace_once(
    "src/gpt_windows_connector/settings_ui.py",
    'def _default_node_id() -> str:\n    machine = os.environ.get("COMPUTERNAME") or socket.gethostname() or "windows-node"\n    return f"{machine}-{uuid.getnode():012x}".lower()\n',
    'def _default_node_id() -> str:\n    return f"lucas-{uuid.uuid4().hex}"\n',
)

# 3) Temporary access has a real TTL and unique grant id.
replace_once(
    "src/gpt_windows_connector/node.py",
    '        session_grants: dict[str, dict[str, object]] = {}\n\n        def effective_access(actor: dict[str, object]) -> dict[str, object] | None:\n',
    '        session_grants: dict[str, dict[str, object]] = {}\n        access_file_mtime = ACCESS_FILE.stat().st_mtime if ACCESS_FILE.exists() else 0.0\n\n        def effective_access(actor: dict[str, object]) -> dict[str, object] | None:\n',
)
replace_once(
    "src/gpt_windows_connector/node.py",
    '            temporary = session_grants.get(user_id)\n            if temporary:\n                return dict(temporary)\n',
    '            temporary = session_grants.get(user_id)\n            if temporary:\n                if float(temporary.get("expires_at") or 0) > time.time():\n                    return dict(temporary)\n                session_grants.pop(user_id, None)\n',
)
replace_once(
    "src/gpt_windows_connector/node.py",
    '            grant = {"user_id": user_id, "email": str(actor.get("email") or ""), "name": str(actor.get("name") or ""), "preset": preset, "security": security, "allowed_roots": roots}\n',
    '            grant = {"user_id": user_id, "email": str(actor.get("email") or ""), "name": str(actor.get("name") or ""), "preset": preset, "security": security, "allowed_roots": roots}\n            if choice == "once":\n                grant["grant_id"] = uuid.uuid4().hex\n                grant["expires_at"] = time.time() + 3600\n',
)

# 4) Per-user policy can never override the Node-wide policy.
replace_once(
    "src/gpt_windows_connector/node.py",
    '                user_config = _load_config()\n                user_config["security"] = dict(access.get("security") or preset_security(str(access.get("preset") or "request_approval")))\n                active_executor = Executor(roots, user_config)\n',
    '                user_config = _load_config()\n                node_security = user_config.get("security") if isinstance(user_config.get("security"), dict) else {}\n                account_security = access.get("security") if isinstance(access.get("security"), dict) else preset_security(str(access.get("preset") or "request_approval"))\n                user_config["security"] = intersect_security(dict(node_security), dict(account_security))\n                active_executor = Executor(roots, user_config)\n',
)

# 5) Node publishes only already-authorized user IDs to seed/reconcile Gateway bindings.
replace_once(
    "src/gpt_windows_connector/node.py",
    '            "node_token": token,\n            "allowed_roots": [str(path) for path in settings.allowed_roots],\n',
    '            "node_token": token,\n            "allowed_roots": [str(path) for path in settings.allowed_roots],\n            "authorized_user_ids": [str(item.get("user_id")) for item in local_access.list_users() if item.get("enabled", True) and item.get("user_id")],\n',
)
replace_once(
    "src/gpt_windows_connector/node.py",
    '        send_lock = asyncio.Lock()\n        request_tasks: set[asyncio.Task[None]] = set()\n\n        async def send_json(payload: dict[str, object]) -> None:\n',
    '        send_lock = asyncio.Lock()\n        request_tasks: set[asyncio.Task[None]] = set()\n\n        async def send_json(payload: dict[str, object]) -> None:\n',
)
replace_once(
    "src/gpt_windows_connector/node.py",
    '        async def send_json(payload: dict[str, object]) -> None:\n            async with send_lock:\n                await ws.send(json.dumps(payload, ensure_ascii=False))\n\n        async def execute_request',
    '        async def send_json(payload: dict[str, object]) -> None:\n            async with send_lock:\n                await ws.send(json.dumps(payload, ensure_ascii=False))\n\n        async def sync_local_access_if_changed() -> None:\n            nonlocal access_file_mtime\n            current = ACCESS_FILE.stat().st_mtime if ACCESS_FILE.exists() else 0.0\n            if current == access_file_mtime:\n                return\n            access_file_mtime = current\n            user_ids = [str(item.get("user_id")) for item in local_access.list_users() if item.get("enabled", True) and item.get("user_id")]\n            await send_json({"type": "access.sync", "authorized_user_ids": user_ids})\n\n        async def execute_request',
)
replace_once(
    "src/gpt_windows_connector/node.py",
    '                _write_status("Online")\n                message = json.loads(raw)\n',
    '                _write_status("Online")\n                await sync_local_access_if_changed()\n                message = json.loads(raw)\n',
)
replace_once(
    "src/gpt_windows_connector/node.py",
    '                    await send_json({"type": "heartbeat", "time": time.time()})\n                    _write_status("Online")\n                    continue\n',
    '                    await send_json({"type": "heartbeat", "time": time.time()})\n                    await sync_local_access_if_changed()\n                    _write_status("Online")\n                    continue\n',
)

# 6) Gateway: remove legacy node ownership/permission schema, hash device tokens, add user-node bindings.
replace_once(
    "src/gpt_windows_connector/gateway.py",
    'import secrets\n',
    'import secrets\nimport hashlib\n',
)
replace_once(
    "src/gpt_windows_connector/gateway.py",
    '            columns = {row[1] for row in db.execute("PRAGMA table_info(nodes)").fetchall()}\n            if "permission_level" not in columns:\n                db.execute("ALTER TABLE nodes ADD COLUMN permission_level TEXT NOT NULL DEFAULT \'operate\'")\n            if "allowed_roots" not in columns:\n                db.execute("ALTER TABLE nodes ADD COLUMN allowed_roots TEXT NOT NULL DEFAULT \'[]\'")\n',
    '            columns = {row[1] for row in db.execute("PRAGMA table_info(nodes)").fetchall()}\n            if "allowed_roots" not in columns:\n                db.execute("ALTER TABLE nodes ADD COLUMN allowed_roots TEXT NOT NULL DEFAULT \'[]\'")\n            if "owner_user_id" in columns or "permission_level" in columns:\n                db.execute("ALTER TABLE nodes RENAME TO nodes_legacy")\n                db.execute("CREATE TABLE nodes (node_id TEXT PRIMARY KEY, name TEXT NOT NULL, token TEXT NOT NULL, updated_at REAL NOT NULL, allowed_roots TEXT NOT NULL DEFAULT \'[]\')")\n                legacy_cols = {row[1] for row in db.execute("PRAGMA table_info(nodes_legacy)").fetchall()}\n                allowed_expr = "allowed_roots" if "allowed_roots" in legacy_cols else "\'[]\'"\n                db.execute(f"INSERT INTO nodes(node_id,name,token,updated_at,allowed_roots) SELECT node_id,name,token,updated_at,{allowed_expr} FROM nodes_legacy")\n                db.execute("DROP TABLE nodes_legacy")\n            db.execute("CREATE TABLE IF NOT EXISTS user_node_bindings (user_id TEXT NOT NULL, node_id TEXT NOT NULL, approved_at REAL NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY(user_id,node_id))")\n',
)
replace_once(
    "src/gpt_windows_connector/gateway.py",
    '                INSERT INTO nodes(node_id,owner_user_id,name,token,updated_at,permission_level,allowed_roots) VALUES(?,?,?,?,?,?,?)\n                ON CONFLICT(node_id) DO UPDATE SET name=excluded.name,token=excluded.token,updated_at=excluded.updated_at,allowed_roots=excluded.allowed_roots\n                """,\n                (node_id, "", name, token, time.time(), "operate", roots_json),\n',
    '                INSERT INTO nodes(node_id,name,token,updated_at,allowed_roots) VALUES(?,?,?,?,?)\n                ON CONFLICT(node_id) DO UPDATE SET name=excluded.name,token=excluded.token,updated_at=excluded.updated_at,allowed_roots=excluded.allowed_roots\n                """,\n                (node_id, name, token, time.time(), roots_json),\n',
)
replace_once(
    "src/gpt_windows_connector/gateway.py",
    '    async def update_config(self, node_id: str, name: str, allowed_roots: list[str]) -> dict:\n',
    '    async def update_token(self, node_id: str, token: str) -> None:\n        with self._connect() as db:\n            db.execute("UPDATE nodes SET token=?,updated_at=? WHERE node_id=?", (token, time.time(), node_id))\n\n    async def update_config(self, node_id: str, name: str, allowed_roots: list[str]) -> dict:\n',
)
replace_once(
    "src/gpt_windows_connector/gateway.py",
    'auth_store = NodeAuthStore(db_path)\n\n\n\n@dataclass\nclass NodeConnection:',
    'auth_store = NodeAuthStore(db_path)\n\n\ndef _token_digest(token: str) -> str:\n    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()\n\n\nclass UserNodeBindingStore:\n    def __init__(self, path: Path) -> None:\n        self.path = path\n\n    def _connect(self) -> sqlite3.Connection:\n        db = sqlite3.connect(self.path, timeout=30)\n        db.row_factory = sqlite3.Row\n        return db\n\n    def node_ids(self, user_id: str) -> list[str]:\n        with self._connect() as db:\n            return [str(r[0]) for r in db.execute("SELECT node_id FROM user_node_bindings WHERE user_id=? ORDER BY updated_at DESC", (user_id,)).fetchall()]\n\n    def users_for_node(self, node_id: str) -> set[str]:\n        with self._connect() as db:\n            return {str(r[0]) for r in db.execute("SELECT user_id FROM user_node_bindings WHERE node_id=?", (node_id,)).fetchall()}\n\n    def upsert(self, user_id: str, node_id: str) -> None:\n        now = time.time()\n        with self._connect() as db:\n            db.execute("INSERT INTO user_node_bindings(user_id,node_id,approved_at,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id,node_id) DO UPDATE SET updated_at=excluded.updated_at", (user_id,node_id,now,now))\n\n    def remove(self, user_id: str, node_id: str) -> None:\n        with self._connect() as db:\n            db.execute("DELETE FROM user_node_bindings WHERE user_id=? AND node_id=?", (user_id,node_id))\n\n    def reconcile_node(self, node_id: str, authorized_user_ids: list[str]) -> tuple[set[str], set[str]]:\n        wanted = {str(v) for v in authorized_user_ids if str(v).strip()}\n        current = self.users_for_node(node_id)\n        for user_id in wanted:\n            self.upsert(user_id, node_id)\n        for user_id in current - wanted:\n            self.remove(user_id, node_id)\n        return wanted - current, current - wanted\n\n\nbindings = UserNodeBindingStore(db_path)\n\n\n@dataclass\nclass NodeConnection:',
)
replace_once(
    "src/gpt_windows_connector/gateway.py",
    '        for node in tuple(self.nodes.values()):\n            try:\n                access = await self.rpc(node.node_id, user.id, "access.check", {}, actor=actor, timeout=3.0)\n',
    '        for node_id in bindings.node_ids(user.id):\n            node = self.nodes.get(node_id)\n            if not node:\n                continue\n            try:\n                access = await self.rpc(node.node_id, user.id, "access.check", {}, actor=actor, timeout=3.0)\n',
)
replace_once(
    "src/gpt_windows_connector/gateway.py",
    '            if not isinstance(access, dict) or not access.get("authorized"):\n                continue\n',
    '            if not isinstance(access, dict) or not access.get("authorized"):\n                bindings.remove(user.id, node.node_id)\n                continue\n',
)
replace_once(
    "src/gpt_windows_connector/gateway.py",
    '    result = await registry.rpc(node_id, user.id, "access.request", {"connection_code": connection_code}, actor=_actor(user), timeout=180.0)\n    auth.audit(user.id, "node.access_request", node_id, {"authorized": bool(isinstance(result, dict) and result.get("authorized"))})\n    return result\n',
    '    if not registration_security.allow(f"node-access:{user.id}:{node_id}", 5, 60):\n        raise PermissionError("Too many connection attempts. Try again in a minute.")\n    result = await registry.rpc(node_id, user.id, "access.request", {"connection_code": connection_code}, actor=_actor(user), timeout=180.0)\n    if isinstance(result, dict) and result.get("authorized"):\n        bindings.upsert(user.id, node_id)\n    auth.audit(user.id, "node.access_request", node_id, {"authorized": bool(isinstance(result, dict) and result.get("authorized"))})\n    return result\n',
)
replace_once(
    "src/gpt_windows_connector/gateway.py",
    '        supplied_token = str(hello.get("node_token") or "").strip()\n',
    '        supplied_token = str(hello.get("node_token") or "").strip()\n        authorized_user_ids = [str(v) for v in hello.get("authorized_user_ids") or [] if str(v).strip()]\n',
)
replace_once(
    "src/gpt_windows_connector/gateway.py",
    '        if record:\n            authorized = secrets.compare_digest(str(record["token"]), supplied_token)\n        else:\n            await auth_store.save(node_id, name, supplied_token, hello_roots)\n',
    '        if record:\n            stored_token = str(record["token"] or "")\n            if stored_token.startswith("sha256:"):\n                authorized = secrets.compare_digest(stored_token, _token_digest(supplied_token))\n            else:\n                authorized = secrets.compare_digest(stored_token, supplied_token)\n                if authorized:\n                    await auth_store.update_token(node_id, _token_digest(supplied_token))\n        else:\n            await auth_store.save(node_id, name, _token_digest(supplied_token), hello_roots)\n',
)
replace_once(
    "src/gpt_windows_connector/gateway.py",
    '        registry.nodes[node_id] = connection\n        await websocket.send_json({"type": "welcome", "ok": True, "config": {"local_security_authority": True, "multi_user_access": True, "pairing_required": False}})\n',
    '        registry.nodes[node_id] = connection\n        bindings.reconcile_node(node_id, authorized_user_ids)\n        await websocket.send_json({"type": "welcome", "ok": True, "config": {"local_security_authority": True, "multi_user_access": True, "pairing_required": False}})\n',
)
replace_once(
    "src/gpt_windows_connector/gateway.py",
    '            elif message.get("type") == "response":\n                registry.resolve(node_id, message)\n',
    '            elif message.get("type") == "response":\n                registry.resolve(node_id, message)\n            elif message.get("type") == "access.sync":\n                _, removed = bindings.reconcile_node(node_id, [str(v) for v in message.get("authorized_user_ids") or []])\n                for user_id in removed:\n                    current = registry.control_locks.get(node_id)\n                    if current and current.owner_user_id == user_id:\n                        registry.control_locks.pop(node_id, None)\n                    await dashboard_events.publish(user_id, "node.remove", {"node_id": node_id})\n',
)

# 7) Web API uses the same rate limit and records the binding only after local approval.
replace_once(
    "src/gpt_windows_connector/webapp.py",
    '        gateway.registry.require_online(node_id)\n        result = await gateway.registry.rpc(node_id, user.id, "access.request", {"connection_code": connection_code}, actor=gateway._actor(user), timeout=180.0)\n        gateway.auth.audit(user.id, "node.access_request", node_id, {"authorized": bool(isinstance(result, dict) and result.get("authorized"))})\n',
    '        gateway.registry.require_online(node_id)\n        if not gateway.registration_security.allow(f"node-access:{user.id}:{node_id}", 5, 60):\n            return JSONResponse({"error": "Too many connection attempts. Try again in a minute."}, status_code=429)\n        result = await gateway.registry.rpc(node_id, user.id, "access.request", {"connection_code": connection_code}, actor=gateway._actor(user), timeout=180.0)\n        if isinstance(result, dict) and result.get("authorized"):\n            gateway.bindings.upsert(user.id, node_id)\n        gateway.auth.audit(user.id, "node.access_request", node_id, {"authorized": bool(isinstance(result, dict) and result.get("authorized"))})\n',
)

# 8) Remove the obsolete read/operate/admin policy module and its dedicated tests after verifying no live imports remain.
for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "tests").rglob("*.py")):
    if path.name in {"permissions.py", "test_permissions.py"}:
        continue
    text = path.read_text(encoding="utf-8")
    if "gpt_windows_connector.permissions" in text or "from .permissions" in text or "NodePolicy" in text:
        raise SystemExit(f"legacy permission model still imported by {path.relative_to(ROOT)}")
(ROOT / "src/gpt_windows_connector/permissions.py").unlink(missing_ok=True)
(ROOT / "tests/test_permissions.py").unlink(missing_ok=True)

# 9) Regression tests for the hard permission ceiling.
(ROOT / "tests/test_access_hardening.py").write_text('''from gpt_windows_connector.access_control import intersect_security\n\n\ndef test_user_full_access_cannot_override_node_ask():\n    node = {"approval_policy": {"file_delete": "ask"}, "network_external": "block", "network_lan": "allow", "block_silent_network": True}\n    user = {"approval_policy": {"file_delete": "allow"}, "network_external": "allow", "network_lan": "allow", "block_silent_network": False}\n    effective = intersect_security(node, user)\n    assert effective["approval_policy"]["file_delete"] == "ask"\n    assert effective["network_external"] == "block"\n    assert effective["block_silent_network"] is True\n\n\ndef test_domain_constraints_only_get_narrower():\n    node = {"allowed_domains": ["example.com", "api.example.com"]}\n    user = {"allowed_domains": ["api.example.com", "other.com"]}\n    assert intersect_security(node, user)["allowed_domains"] == ["api.example.com"]\n''', encoding="utf-8")

print("Lucas access hardening patch applied")
