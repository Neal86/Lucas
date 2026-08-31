from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import secrets
import socket
import sys
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlencode

import websockets

from .access_control import LocalAccessStore, clamp_roots, normalize_preset, preset_security
from .config import NodeSettings
from .executor import Executor
from .i18n import tr
from .settings_ui import configure_gui as _configure_gui
from .task_runs import TaskRunStore

APP_NAME = "Lucas"
CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "node-config.json"
LOG_FILE = CONFIG_DIR / "lucas-node.log"
STATUS_FILE = CONFIG_DIR / "node-status.json"
TASK_RUNS_FILE = CONFIG_DIR / "task-runs.db"
ACCESS_FILE = CONFIG_DIR / "node-access.json"
local_task_runs = TaskRunStore(TASK_RUNS_FILE)
local_access = LocalAccessStore(ACCESS_FILE)
DEFAULT_GATEWAY = "wss://lucasmcp.com/ws/node"
log = logging.getLogger("lucas.node")


def _acquire_node_mutex() -> object | None:
    if sys.platform != "win32":
        return object()
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, "Local\\LucasNodeSingleInstance")
        if not handle:
            return None
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return None
        return handle
    except Exception:
        log.exception("Could not create node single-instance mutex")
        return object()


def _default_node_id() -> str:
    machine = os.environ.get("COMPUTERNAME") or socket.gethostname() or "windows-node"
    return f"{machine}-{uuid.getnode():012x}".lower()


def _load_config() -> dict[str, object]:
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_config(config: dict[str, object]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(CONFIG_FILE)


def _write_status(status: str, detail: str = "") -> None:
    """Best-effort status publishing; UI file-lock races must never drop WebSocket."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_FILE.with_name(f"{STATUS_FILE.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps({"status": status, "detail": detail, "time": time.time(), "pid": os.getpid(), "source": "node"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for attempt in range(5):
            try:
                temporary.replace(STATUS_FILE)
                return
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(0.02 * (attempt + 1))
    except OSError as exc:
        log.debug("Could not update status file: %s", exc)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _legacy_configure_gui(existing: dict[str, object]) -> dict[str, object] | None:
    try:
        import ctypes
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception as exc:
        raise RuntimeError(f"Lucas configuration UI is unavailable: {exc}") from exc

    colors = {
        "window": "#F4F6F8", "sidebar": "#FFFFFF", "card": "#FFFFFF", "border": "#E5E7EB",
        "text": "#111827", "muted": "#667085", "accent": "#2563EB", "accent_soft": "#EFF6FF",
        "green": "#15803D", "green_soft": "#F0FDF4", "orange": "#B45309", "orange_soft": "#FFF7ED",
        "red": "#B42318", "red_soft": "#FEF3F2",
    }
    font = "Segoe UI"
    result: dict[str, object] | None = None
    root = tk.Tk()
    root.title("Lucas Settings")
    root.geometry("920x650")
    root.minsize(840, 600)
    root.configure(bg=colors["window"])

    gateway = tk.StringVar(value=str(existing.get("gateway_ws_url") or DEFAULT_GATEWAY))
    node_id = tk.StringVar(value=str(existing.get("node_id") or _default_node_id()))
    node_name = tk.StringVar(value=str(existing.get("node_name") or os.environ.get("COMPUTERNAME") or socket.gethostname()))
    stored_permission = str(existing.get("permission_level") or "operate").lower()
    if stored_permission not in {"read", "operate", "admin"}:
        stored_permission = "operate"
    permission = tk.StringVar(value=stored_permission)
    roots = [str(item) for item in existing.get("allowed_roots", []) if str(item).strip()]
    if not roots:
        roots = [str(Path.home().resolve())]
    try:
        is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        is_admin = False

    sidebar = tk.Frame(root, bg=colors["sidebar"], width=220, highlightthickness=1, highlightbackground=colors["border"])
    sidebar.pack(side="left", fill="y")
    sidebar.pack_propagate(False)
    brand = tk.Frame(sidebar, bg=colors["sidebar"])
    brand.pack(fill="x", padx=22, pady=(24, 26))
    tk.Label(brand, text="L", bg=colors["accent"], fg="#FFFFFF", font=(font, 14, "bold"), width=2, height=1).pack(side="left")
    tk.Label(brand, text="Lucas", bg=colors["sidebar"], fg=colors["text"], font=(font, 16, "bold")).pack(side="left", padx=(10, 0))
    nav_container = tk.Frame(sidebar, bg=colors["sidebar"])
    nav_container.pack(fill="x", padx=12)
    content = tk.Frame(root, bg=colors["window"])
    content.pack(side="left", fill="both", expand=True)

    header = tk.Frame(content, bg=colors["window"])
    header.pack(fill="x", padx=34, pady=(28, 18))
    title_var = tk.StringVar(value="General")
    subtitle_var = tk.StringVar(value="Connection identity and local Lucas configuration.")
    tk.Label(header, textvariable=title_var, bg=colors["window"], fg=colors["text"], font=(font, 22, "bold")).pack(anchor="w")
    tk.Label(header, textvariable=subtitle_var, bg=colors["window"], fg=colors["muted"], font=(font, 10)).pack(anchor="w", pady=(5, 0))

    local_banner = tk.Frame(content, bg=colors["green_soft"], highlightthickness=1, highlightbackground="#BBF7D0")
    local_banner.pack(fill="x", padx=34, pady=(0, 18))
    tk.Label(local_banner, text="Security settings are local-only", bg=colors["green_soft"], fg=colors["green"], font=(font, 10, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
    tk.Label(local_banner, text="The Lucas website can display this policy, but it cannot change permissions or allowed folders on this computer.", bg=colors["green_soft"], fg="#166534", font=(font, 9), wraplength=610, justify="left").pack(anchor="w", padx=14, pady=(0, 10))

    page_host = tk.Frame(content, bg=colors["window"])
    page_host.pack(fill="both", expand=True, padx=34)
    pages: dict[str, tk.Frame] = {}
    nav_buttons: dict[str, tk.Button] = {}

    def make_page(name: str) -> tk.Frame:
        page = tk.Frame(page_host, bg=colors["window"])
        pages[name] = page
        return page

    def card(parent: tk.Widget, heading: str, description: str = "") -> tk.Frame:
        box = tk.Frame(parent, bg=colors["card"], highlightthickness=1, highlightbackground=colors["border"])
        box.pack(fill="x", pady=(0, 14))
        tk.Label(box, text=heading, bg=colors["card"], fg=colors["text"], font=(font, 11, "bold")).pack(anchor="w", padx=18, pady=(16, 2))
        if description:
            tk.Label(box, text=description, bg=colors["card"], fg=colors["muted"], font=(font, 9), wraplength=610, justify="left").pack(anchor="w", padx=18, pady=(0, 12))
        return box

    def field(parent: tk.Widget, label: str, variable: tk.StringVar, *, readonly: bool = False) -> None:
        row = tk.Frame(parent, bg=colors["card"])
        row.pack(fill="x", padx=18, pady=(0, 13))
        tk.Label(row, text=label, bg=colors["card"], fg=colors["text"], font=(font, 9, "bold"), width=18, anchor="w").pack(side="left")
        entry = tk.Entry(row, textvariable=variable, font=(font, 10), relief="flat", bd=0, bg="#F9FAFB" if readonly else "#FFFFFF", fg=colors["muted"] if readonly else colors["text"], readonlybackground="#F9FAFB")
        entry.pack(side="left", fill="x", expand=True, ipady=8)
        if readonly:
            entry.configure(state="readonly")

    general = make_page("General")
    identity = card(general, "Computer", "This identifies the Windows computer connected to your Lucas account.")
    field(identity, "Computer name", node_name)
    field(identity, "Node ID", node_id, readonly=True)
    connection = card(general, "Connection", "The Node ID and device credential are stored only on this computer.")
    field(connection, "Gateway", gateway)

    permissions = make_page("Permissions")
    mode_card = card(permissions, "Security mode", "Choose the maximum level of actions an AI may perform through this Lucas Node.")
    modes = [
        ("read", "Safe", "Read-only", "Inspect files and information without modifying projects.", colors["green_soft"], colors["green"]),
        ("operate", "Standard", "Recommended", "Work inside allowed folders, run normal tools, and modify project files.", colors["accent_soft"], colors["accent"]),
        ("admin", "Full Access", "Advanced", "Permit Lucas admin-class operations. Windows may still require elevated OS privileges.", colors["red_soft"], colors["red"]),
    ]
    for value, name, badge, desc, bg, fg in modes:
        item = tk.Frame(mode_card, bg=bg, highlightthickness=1, highlightbackground=colors["border"])
        item.pack(fill="x", padx=18, pady=(0, 10))
        tk.Radiobutton(item, variable=permission, value=value, text=name, bg=bg, fg=colors["text"], activebackground=bg, activeforeground=colors["text"], selectcolor="#FFFFFF", font=(font, 10, "bold"), anchor="w").pack(side="left", padx=(12, 8), pady=12)
        copy = tk.Frame(item, bg=bg)
        copy.pack(side="left", fill="x", expand=True, pady=8)
        tk.Label(copy, text=badge, bg=bg, fg=fg, font=(font, 8, "bold")).pack(anchor="w")
        tk.Label(copy, text=desc, bg=bg, fg=colors["muted"], font=(font, 9), wraplength=470, justify="left").pack(anchor="w", pady=(2, 0))

    folders = make_page("Folders")
    folder_card = card(folders, "Allowed folders", "AI file access is restricted to these local folders. Add only folders you want Lucas to expose.")
    list_frame = tk.Frame(folder_card, bg=colors["card"])
    list_frame.pack(fill="both", expand=True, padx=18, pady=(0, 12))
    roots_list = tk.Listbox(list_frame, height=11, font=(font, 10), bg="#F9FAFB", fg=colors["text"], selectbackground=colors["accent_soft"], selectforeground=colors["text"], relief="flat", bd=0, highlightthickness=1, highlightbackground=colors["border"])
    roots_list.pack(side="left", fill="both", expand=True)
    for item in roots:
        roots_list.insert("end", item)
    folder_actions = tk.Frame(list_frame, bg=colors["card"])
    folder_actions.pack(side="left", fill="y", padx=(10, 0))

    def solid_button(parent: tk.Widget, text: str, command, *, primary: bool = False, danger: bool = False) -> tk.Button:
        bg = colors["accent"] if primary else (colors["red_soft"] if danger else "#FFFFFF")
        fg = "#FFFFFF" if primary else (colors["red"] if danger else colors["text"])
        return tk.Button(parent, text=text, command=command, font=(font, 9, "bold"), bg=bg, fg=fg, activebackground=bg, activeforeground=fg, relief="flat", bd=0, cursor="hand2", padx=13, pady=8, highlightthickness=1, highlightbackground=colors["border"])

    def add_root() -> None:
        selected = filedialog.askdirectory(title="Choose a folder Lucas may access")
        if selected and selected not in roots_list.get(0, "end"):
            roots_list.insert("end", selected)

    def remove_root() -> None:
        selected = roots_list.curselection()
        if selected:
            roots_list.delete(selected[0])

    solid_button(folder_actions, "Add folder", add_root, primary=True).pack(fill="x", pady=(0, 8))
    solid_button(folder_actions, "Remove", remove_root, danger=True).pack(fill="x")

    system_page = make_page("System Access")
    access = card(system_page, "Windows privileges", "Lucas application permissions and Windows administrator privileges are separate security layers.")
    status_bg = colors["green_soft"] if is_admin else colors["orange_soft"]
    status_fg = colors["green"] if is_admin else colors["orange"]
    status_text = "Administrator" if is_admin else "Standard user"
    state = tk.Frame(access, bg=status_bg, highlightthickness=1, highlightbackground=colors["border"])
    state.pack(fill="x", padx=18, pady=(0, 14))
    tk.Label(state, text=status_text, bg=status_bg, fg=status_fg, font=(font, 10, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
    tk.Label(state, text=("Windows currently allows elevated system operations." if is_admin else "System services, protected registry changes, drivers, and some hardware controls may require Lucas to be started as administrator."), bg=status_bg, fg=colors["muted"], font=(font, 9), wraplength=560, justify="left").pack(anchor="w", padx=14, pady=(0, 10))
    tk.Label(access, text="Changing Permission mode to Full Access does not bypass Windows UAC.", bg=colors["card"], fg=colors["muted"], font=(font, 9)).pack(anchor="w", padx=18, pady=(0, 16))

    descriptions = {
        "General": "Connection identity and local Lucas configuration.",
        "Permissions": "Set the local security boundary for AI operations.",
        "Folders": "Choose exactly which folders Lucas may expose to AI clients.",
        "System Access": "Review Windows privilege state for protected system operations.",
    }

    def show_page(name: str) -> None:
        for page in pages.values():
            page.pack_forget()
        pages[name].pack(fill="both", expand=True)
        title_var.set(name)
        subtitle_var.set(descriptions[name])
        for key, button in nav_buttons.items():
            button.configure(bg=colors["accent_soft"], fg=colors["accent"]) if key == name else button.configure(bg=colors["sidebar"], fg=colors["muted"])

    for name in ("General", "Permissions", "Folders", "System Access"):
        button = tk.Button(nav_container, text=name, command=lambda n=name: show_page(n), bg=colors["sidebar"], fg=colors["muted"], activebackground=colors["accent_soft"], activeforeground=colors["accent"], relief="flat", bd=0, anchor="w", font=(font, 10, "bold"), padx=12, pady=10, cursor="hand2")
        button.pack(fill="x", pady=2)
        nav_buttons[name] = button
    tk.Label(sidebar, text="Permissions are controlled\non this computer.", bg=colors["sidebar"], fg=colors["muted"], font=(font, 8), justify="left").pack(side="bottom", anchor="w", padx=24, pady=22)

    footer = tk.Frame(content, bg=colors["window"])
    footer.pack(fill="x", padx=34, pady=(10, 24))

    def save() -> None:
        nonlocal result
        gateway_value = gateway.get().strip()
        roots_value = [str(Path(value).expanduser().resolve()) for value in roots_list.get(0, "end") if str(value).strip()]
        if not gateway_value.startswith(("ws://", "wss://")):
            messagebox.showerror(APP_NAME, "Gateway URL must start with ws:// or wss://")
            return
        if not node_name.get().strip() or not node_id.get().strip():
            messagebox.showerror(APP_NAME, "Computer name and Node ID are required.")
            return
        if not roots_value or any(not Path(value).is_dir() for value in roots_value):
            messagebox.showerror(APP_NAME, "Every allowed folder must exist on this Windows PC.")
            return
        updated = dict(existing)
        updated.update({
            "gateway_ws_url": gateway_value.rstrip("/"), "node_name": node_name.get().strip(), "node_id": node_id.get().strip(),
            "permission_level": permission.get(), "allowed_roots": roots_value,
        })
        updated.setdefault("connection_enabled", True)
        updated.setdefault("launch_at_startup", True)
        _save_config(updated)
        result = updated
        root.destroy()

    solid_button(footer, "Cancel", root.destroy).pack(side="right")
    solid_button(footer, "Save changes", save, primary=True).pack(side="right", padx=(0, 10))
    show_page("General")
    root.mainloop()
    return result


def _apply_config(config: dict[str, object]) -> None:
    mapping = {
        "GWC_GATEWAY_WS": config.get("gateway_ws_url"),
        "GWC_NODE_ID": config.get("node_id"),
        "GWC_NODE_NAME": config.get("node_name"),
        "GWC_PERMISSION_LEVEL": config.get("permission_level"),
    }
    for key, value in mapping.items():
        if value is not None and str(value).strip():
            os.environ[key] = str(value).strip()
    roots = config.get("allowed_roots")
    if isinstance(roots, list) and roots:
        os.environ["GWC_ALLOWED_ROOTS"] = os.pathsep.join(str(item) for item in roots)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("GWC_NODE_STATE", str(CONFIG_DIR / "node-state.json"))


def _setup_logging() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not root_logger.handlers:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root_logger.addHandler(console)
    if not any(isinstance(handler, RotatingFileHandler) for handler in root_logger.handlers):
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def _load_saved_token(settings: NodeSettings) -> str:
    if settings.node_token:
        return settings.node_token
    try:
        data = json.loads(settings.state_file.read_text(encoding="utf-8"))
        token = str(data.get("node_token") or "").strip()
        if token:
            return token
    except (OSError, json.JSONDecodeError):
        pass
    token = secrets.token_urlsafe(32)
    _save_token(settings, token)
    return token


def _save_token(settings: NodeSettings, token: str) -> None:
    settings.state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = settings.state_file.with_suffix(".tmp")
    temporary.write_text(json.dumps({"node_id": settings.node_id, "node_token": token}, indent=2), encoding="utf-8")
    temporary.replace(settings.state_file)


def _prompt_access_request(actor: dict[str, object], requested_permission: str, node_roots: list[str]) -> dict[str, object]:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:
        return {"decision": "deny", "error": f"approval UI unavailable: {exc}"}

    result: dict[str, object] = {"decision": "deny"}
    root = tk.Tk()
    root.title(tr("Lucas 访问请求", "Lucas Access Request"))
    root.geometry("560x520")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    frame = tk.Frame(root, padx=24, pady=22)
    frame.pack(fill="both", expand=True)
    display = str(actor.get("name") or actor.get("email") or actor.get("user_id") or tr("未知用户", "Unknown user"))
    email = str(actor.get("email") or "")
    tk.Label(frame, text=tr("新的 Lucas 用户请求访问此电脑", "A Lucas user is requesting access to this computer"), font=("Segoe UI", 15, "bold")).pack(anchor="w")
    tk.Label(frame, text=display, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(18, 2))
    if email and email != display:
        tk.Label(frame, text=email, font=("Segoe UI", 9), fg="#666666").pack(anchor="w")
    tk.Label(frame, text=tr("只有你在此电脑上批准后，该用户才能通过 Lucas 执行操作。", "This account can use Lucas on this computer only after you approve it locally."), font=("Segoe UI", 9), fg="#555555", wraplength=500, justify="left").pack(anchor="w", pady=(10, 18))

    tk.Label(frame, text=tr("权限", "Permission"), font=("Segoe UI", 9, "bold")).pack(anchor="w")
    permission = tk.StringVar(value=requested_permission if requested_permission in {"read", "operate", "admin"} else "operate")
    ttk.Combobox(frame, textvariable=permission, values=["read", "operate", "admin"], state="readonly", width=24).pack(anchor="w", pady=(5, 14))

    tk.Label(frame, text=tr("允许访问的文件夹", "Allowed folders"), font=("Segoe UI", 9, "bold")).pack(anchor="w")
    folders = tk.Listbox(frame, selectmode="multiple", height=min(max(len(node_roots), 4), 9), width=70)
    folders.pack(fill="x", pady=(5, 8))
    for index, path in enumerate(node_roots):
        folders.insert("end", path)
        folders.selection_set(index)
    tk.Label(frame, text=tr("权限不能超过此 Node 的总权限，文件夹也不能超出 Allowed Folders。", "Account permission cannot exceed the Node maximum, and folders cannot exceed Allowed Folders."), font=("Segoe UI", 8), fg="#777777").pack(anchor="w")

    actions = tk.Frame(frame)
    actions.pack(side="bottom", fill="x", pady=(24, 0))

    def finish(decision: str) -> None:
        selected = [node_roots[i] for i in folders.curselection()]
        result.update({"decision": decision, "permission_level": permission.get(), "allowed_roots": selected})
        root.destroy()

    tk.Button(actions, text=tr("拒绝", "Deny"), command=lambda: finish("deny"), padx=14, pady=7).pack(side="right")
    tk.Button(actions, text=tr("允许一次", "Allow once"), command=lambda: finish("once"), padx=14, pady=7).pack(side="right", padx=(0, 8))
    tk.Button(actions, text=tr("始终允许", "Always allow"), command=lambda: finish("always"), padx=14, pady=7).pack(side="right", padx=(0, 8))
    root.protocol("WM_DELETE_WINDOW", lambda: finish("deny"))
    root.mainloop()
    return result


async def _serve_connection(settings: NodeSettings, executor: Executor) -> None:
    query = urlencode({"node_id": settings.node_id})
    uri = settings.gateway_ws_url + ("&" if "?" in settings.gateway_ws_url else "?") + query
    token = _load_saved_token(settings)
    async with websockets.connect(uri, ping_interval=20, ping_timeout=20, max_size=32 * 1024 * 1024) as ws:
        await ws.send(json.dumps({
            "type": "hello",
            "node_id": settings.node_id,
            "name": settings.node_name,
            "node_token": token,
            "permission_level": settings.permission_level,
            "allowed_roots": [str(path) for path in settings.allowed_roots],
        }))
        welcome = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        if not welcome.get("ok"):
            raise RuntimeError(welcome.get("error") or "Gateway rejected node")
        # Security policy is authoritative on the Windows computer. The gateway may
        # report status, but it is never allowed to overwrite local permissions.
        log.info("Connected as %s (%s), permission=%s", settings.node_name, settings.node_id, settings.permission_level)
        _write_status("Online")
        node_roots = [str(path) for path in settings.allowed_roots]
        session_grants: dict[str, dict[str, object]] = {}

        def effective_access(actor: dict[str, object]) -> dict[str, object] | None:
            user_id = str(actor.get("user_id") or "").strip()
            if not user_id:
                return None
            temporary = session_grants.get(user_id)
            if temporary:
                return dict(temporary)
            saved = local_access.effective(user_id, settings.permission_level, node_roots)
            return dict(saved) if saved else None

        async def request_access(actor: dict[str, object], requested_permission: str) -> dict[str, object]:
            user_id = str(actor.get("user_id") or "").strip()
            if not user_id:
                return {"authorized": False, "error": "missing user identity"}
            current = effective_access(actor)
            if current:
                return {"authorized": True, **current}
            decision = await asyncio.to_thread(_prompt_access_request, actor, requested_permission, node_roots)
            choice = str(decision.get("decision") or "deny")
            roots = clamp_roots([str(item) for item in decision.get("allowed_roots") or []], node_roots)
            permission_level = clamp_permission(str(decision.get("permission_level") or "read"), settings.permission_level)
            if choice not in {"once", "always"} or not roots:
                log.info("Local access denied for user %s", user_id)
                return {"authorized": False, "decision": "deny"}
            grant = {"user_id": user_id, "email": str(actor.get("email") or ""), "name": str(actor.get("name") or ""), "permission_level": permission_level, "allowed_roots": roots}
            if choice == "always":
                saved = local_access.upsert(actor, permission_level, roots)
                grant.update(saved)
            else:
                session_grants[user_id] = dict(grant)
            log.info("Local access approved for user %s permission=%s mode=%s", user_id, permission_level, choice)
            return {"authorized": True, "decision": choice, **grant}

        send_lock = asyncio.Lock()
        request_tasks: set[asyncio.Task[None]] = set()

        async def send_json(payload: dict[str, object]) -> None:
            async with send_lock:
                await ws.send(json.dumps(payload, ensure_ascii=False))

        async def execute_request(request_id: object, method: str, params: dict, actor: dict[str, object]) -> None:
            wall_started=time.time(); status="success"; error_type=None
            try:
                access = effective_access(actor)
                if not access:
                    raise PermissionError("This Lucas user has not been approved on the Windows Node")
                user_id = str(access.get("user_id") or "")
                roots = tuple(Path(str(item)).resolve() for item in access.get("allowed_roots") or [])
                active_executor = Executor(roots, str(access.get("permission_level") or "read"), _load_config())
                result = await active_executor.call(method, params)
                if user_id and user_id not in session_grants:
                    local_access.touch(user_id)
                response = {"type": "response", "id": request_id, "ok": True, "result": result}
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                status="failed"; error_type=type(exc).__name__
                log.exception("Execution failed: %s", method)
                response = {"type": "response", "id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
            wall_ended=time.time()
            try:
                workspace=str(params.get("workspace") or "")
                local_task_runs.record_operation(owner_id="local",node_id=settings.node_id,action=method,target=workspace or None,started_at=wall_started,ended_at=wall_ended,status=status,details={"error_type":error_type} if error_type else {},context_key=workspace or "default")
            except Exception:
                log.exception("Could not record local Task Run")
            try:
                await send_json(response)
            except Exception:
                log.exception("Failed sending response for %s", method)

        try:
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=15)
                except asyncio.TimeoutError:
                    await send_json({"type": "heartbeat", "time": time.time()})
                    _write_status("Online")
                    continue
                _write_status("Online")
                message = json.loads(raw)
                if message.get("type") != "request":
                    continue
                request_id = message.get("id")
                method = message.get("method", "")
                params = message.get("params") or {}
                actor = message.get("actor") if isinstance(message.get("actor"), dict) else {}
                if method == "access.request":
                    try:
                        result = await request_access(actor, str(params.get("requested_permission") or "operate"))
                        await send_json({"type": "response", "id": request_id, "ok": True, "result": result})
                    except Exception as exc:
                        log.exception("Access approval failed")
                        await send_json({"type": "response", "id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
                    continue
                if method == "access.check":
                    access = effective_access(actor)
                    await send_json({"type": "response", "id": request_id, "ok": True, "result": ({"authorized": True, **access} if access else {"authorized": False})})
                    continue
                if method == "node.configure":
                    await send_json({
                        "type": "response", "id": request_id, "ok": False,
                        "error": "PermissionError: Security settings are local-only. Open Lucas Settings from the Windows tray.",
                    })
                    continue
                if method == "node.logs":
                    log_access = effective_access(actor)
                    if not log_access or str(log_access.get("permission_level") or "read") != "admin":
                        await send_json({"type": "response", "id": request_id, "ok": False, "error": "PermissionError: Admin permission is required for Node logs"})
                        continue
                    try:
                        limit = max(20, min(int(params.get("limit", 200)), 1000))
                        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:] if LOG_FILE.exists() else []
                        await send_json({"type": "response", "id": request_id, "ok": True, "result": {"lines": lines}})
                    except Exception as exc:
                        await send_json({"type": "response", "id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
                    continue

                task = asyncio.create_task(execute_request(request_id, method, params, actor), name=f"lucas:{method}:{request_id}")
                request_tasks.add(task)
                task.add_done_callback(request_tasks.discard)
        finally:
            if request_tasks:
                for task in request_tasks:
                    task.cancel()
                await asyncio.gather(*request_tasks, return_exceptions=True)


async def run_node() -> None:
    delay = 1.0
    while True:
        try:
            config = _load_config()
            _apply_config(config)
            settings = NodeSettings.from_env()
            executor = Executor(settings.allowed_roots, settings.permission_level, config)
            _write_status("Connecting")
            await _serve_connection(settings, executor)
            delay = 1.0
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Disconnected: %s; retrying in %.1fs", exc, delay)
            _write_status("Reconnecting", str(exc))
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)


def main() -> None:
    parser = argparse.ArgumentParser(prog="lucas-node")
    parser.add_argument("--configure", action="store_true", help="Open the Lucas Node configuration window")
    args = parser.parse_args()
    _setup_logging()
    config = _load_config()
    if not config:
        settings = NodeSettings.from_env()
        config = {"gateway_ws_url": settings.gateway_ws_url, "node_id": settings.node_id, "node_name": settings.node_name, "permission_level": settings.permission_level, "allowed_roots": [str(path) for path in settings.allowed_roots]}
        _save_config(config)
    if args.configure:
        updated = _configure_gui(config)
        if updated is not None:
            log.info("Saved local Lucas security settings")
        return
    mutex = _acquire_node_mutex()
    if mutex is None:
        log.info("Another Lucas Node instance is already running; exiting duplicate process")
        return
    _apply_config(config)
    log.info("Lucas Node starting. config=%s log=%s", CONFIG_FILE, LOG_FILE)
    try:
        asyncio.run(run_node())
    except KeyboardInterrupt:
        _write_status("Offline", "Stopped by user")
        log.info("Lucas Node stopped by user.")


if __name__ == "__main__":
    main()
