from __future__ import annotations

import ctypes
import json
import os
import re
import secrets
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any

from .access_control import LocalAccessStore, clamp_roots, normalize_preset, preset_security
from .i18n import localize_tk_tree, system_language, tr
from .task_runs import TaskRunStore

SETTINGS_EN = {
    "搜索设置...": "Search settings...", "常规": "General", "安全": "Security", "用户与权限": "Users & Permissions",
    "文件访问": "File Access", "网络": "Network", "规则": "Rules", "任务记录": "Task History", "系统访问": "System Access",
    "电脑": "Computer", "电脑名称": "Computer name", "Windows 设备名称，只读。网页中的显示名称可单独修改。": "Windows device name, read-only.",
    "设备唯一标识。": "Unique device identifier.", "连接": "Connection", "安全 WebSocket 地址。": "Secure WebSocket address.",
    "连接状态": "Connection status", "实时显示 Lucas Node 与 Gateway 的连接状态。": "Shows the live connection between Lucas Node and the Gateway.",
    "连接方式": "Connection method", "这台电脑使用固定 Node ID 长期在线。其他 Lucas 账号通过 Node ID 发起访问申请，再由本机批准。": "This computer stays online with a fixed Node ID. Other Lucas accounts request access by Node ID and must be approved locally.",
    "无需 Pairing Code": "No pairing code required", "权限": "Permissions", "快捷设置": "Quick settings", "权限来源": "Permission authority", "仅本机": "Local only",
    "审批策略": "Approval policy", "直接允许": "Allow", "需要确认": "Ask", "始终确认": "Always ask", "阻止": "Block",
    "已授权 Lucas 用户": "Authorized Lucas users", "只有在这台电脑上批准过的 Lucas 用户才能操作此 Node。权限和目录以这里的本地设置为最终准则。": "Only Lucas users approved on this computer can operate this Node. Local permissions and folders are authoritative.",
    "选择一个用户": "Select a user", "允许访问的文件夹": "Allowed folders", "用户权限不会超过 Node 总权限，目录不会超出 Allowed Folders。": "User permission cannot exceed the Node maximum and folders cannot exceed Allowed Folders.",
    "保存权限": "Save permissions", "撤销访问": "Revoke access", "刷新": "Refresh", "本地最终授权": "Local final authority",
    "VPS 只负责转发用户身份和请求。是否允许执行、实际权限和允许目录都由此 Windows Node 再次检查。": "The VPS only relays identity and requests. This Windows Node makes the final decision on execution, permissions, and folders.",
    "已启用": "Enabled", "沙箱与文件访问": "Sandbox & file access", "仅允许访问以下文件夹": "Only allow these folders",
    "文件读写、上传、下载与项目工作区都受此列表限制。": "File operations, uploads, downloads, and workspaces are restricted to this list.", "添加文件夹": "Add folder", "移除": "Remove",
    "硬边界": "Hard boundary", "网络访问": "Network access", "外部网络访问": "External network access", "本地局域网访问": "Local network access", "允许的域名": "Allowed domains", "阻止后台静默联网": "Block silent background network access",
    "本地 Rules": "Local Rules", "本地安全规则": "Local security rules", "执行前显示规则摘要": "Show rule summary before execution",
    "Windows 权限": "Windows privileges", "当前 Windows 权限": "Current Windows privilege", "管理员": "Administrator", "标准用户": "Standard user", "未启用": "Disabled", "重要": "Important",
    "保存更改": "Save changes", "恢复默认": "Restore defaults", "取消": "Cancel", "安全策略仅在此电脑上生效": "Security policy applies only on this computer",
    "请求批准（Recommended）": "Ask for approval (Recommended)", "帮我批准": "Auto-approve safe actions", "完全访问权限": "Full Access", "自定义": "Custom",
    "更新 Node": "Update Node", "自动检查新版本；仅检测到新版时显示更新按钮。": "Checks for updates automatically and shows the update button only when a newer version exists."
}

APP_NAME = "Lucas"
DEFAULT_GATEWAY = "wss://lucasmcp.com/ws/node"
CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "node-config.json"
STATE_FILE = CONFIG_DIR / "node-state.json"
STATUS_FILE = CONFIG_DIR / "node-status.json"
TRAY_PID_FILE = CONFIG_DIR / "lucas-tray.pid"
UI_STATE_FILE = CONFIG_DIR / "settings-ui-state.json"
TASK_RUNS_FILE = CONFIG_DIR / "task-runs.db"
ACCESS_FILE = CONFIG_DIR / "node-access.json"
LATEST_VERSION_URL = "https://raw.githubusercontent.com/Neal86/Lucas/main/pyproject.toml"
INSTALLER_URL = "https://raw.githubusercontent.com/Neal86/Lucas/main/scripts/install-node.ps1"

APPROVAL_DEFAULTS = {
    "system_info":"allow","shell":"allow","file_write":"ask","file_delete":"ask",
    "service_control":"ask","process_control":"ask","desktop_control":"ask","screenshots":"allow",
    "clipboard":"ask","browser_control":"ask","browser_transfer":"always_ask","git_write":"ask",
    "git_push":"always_ask","software_install":"always_ask","registry_system":"always_ask","high_risk":"always_ask",
}
PRESETS = {
    "请求批准（Recommended）": {"approval_policy":APPROVAL_DEFAULTS,"network_external":"ask","network_lan":"allow","block_silent_network":True},
    "帮我批准": {"approval_policy":{**{k:"allow" for k in APPROVAL_DEFAULTS},"browser_transfer":"always_ask","git_push":"always_ask","software_install":"always_ask","registry_system":"always_ask","high_risk":"always_ask","service_control":"always_ask"},"network_external":"allow","network_lan":"allow","block_silent_network":False},
    "完全访问权限": {"approval_policy":{k:"allow" for k in APPROVAL_DEFAULTS},"network_external":"allow","network_lan":"allow","block_silent_network":False},
}
PRESET_DESCRIPTIONS = {
    "请求批准（Recommended）":"编辑外部文件和使用互联网时始终询问。",
    "帮我批准":"仅对检测到的高风险操作请求批准。",
    "完全访问权限":"可不受限制地访问互联网和允许目录中的任何文件。",
    "自定义":"使用下方逐项设置。",
}

def detect_security_preset(approval_policy: dict[str,str], network_external: str, network_lan: str, block_silent_network: bool, allowed_domains: list[str] | tuple[str, ...] | None = None) -> str:
    domains = [str(value).strip() for value in (allowed_domains or []) if str(value).strip()]
    for name,preset in PRESETS.items():
        if network_external != preset["network_external"] or network_lan != preset["network_lan"] or bool(block_silent_network) != bool(preset["block_silent_network"]):
            continue
        if name == "完全访问权限" and domains:
            continue
        if all(str(approval_policy.get(k)) == str(v) for k,v in preset["approval_policy"].items()):
            return name
    return "自定义"

def _version_key(value: str) -> tuple[int,...]:
    return tuple(int(x) for x in re.findall(r"\d+", value)[:4]) or (0,)

def _fetch_latest_version(timeout: float = 5.0) -> str | None:
    try:
        request = urllib.request.Request(
            f"{LATEST_VERSION_URL}?t={int(time.time())}",
            headers={"Cache-Control":"no-cache","Pragma":"no-cache","User-Agent":"Lucas-Node-Updater"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text=response.read().decode("utf-8",errors="replace")
        for line in text.splitlines():
            if line.strip().startswith("version ="):
                return line.split("=",1)[1].strip().strip(chr(34)).strip(chr(39))
        return None
    except Exception:
        return None

def _has_saved_token() -> bool:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return bool(str(data.get("node_token") or "").strip()) if isinstance(data, dict) else False
    except (OSError, json.JSONDecodeError):
        return False

def _app_version() -> str:
    try:
        return package_version("gpt-windows-connector")
    except PackageNotFoundError:
        return "dev"

def _default_node_id() -> str:
    return f"lucas-{uuid.uuid4().hex}"

def _save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temp = CONFIG_FILE.with_name(f"{CONFIG_FILE.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(CONFIG_FILE)

def _load_last_page() -> str:
    allowed = {"常规", "安全", "用户与权限", "文件访问", "网络", "规则", "任务记录", "系统访问"}
    try:
        data = json.loads(UI_STATE_FILE.read_text(encoding="utf-8"))
        page = str(data.get("last_page") or "") if isinstance(data, dict) else ""
        return page if page in allowed else "常规"
    except (OSError, json.JSONDecodeError):
        return "常规"

def _save_last_page(page: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        temp = UI_STATE_FILE.with_name(f"{UI_STATE_FILE.name}.{os.getpid()}.tmp")
        temp.write_text(json.dumps({"last_page": page}, ensure_ascii=False), encoding="utf-8")
        temp.replace(UI_STATE_FILE)
    except OSError:
        pass

def _restart_node_for_apply() -> None:
    """Ask the running tray to recreate Node by safely terminating its managed child."""
    try:
        import psutil
        if not TRAY_PID_FILE.exists():
            return
        tray_pid=int(TRAY_PID_FILE.read_text(encoding="ascii").strip())
        tray=psutil.Process(tray_pid)
        tray_cmd=" ".join(tray.cmdline()).lower()
        if "gpt_windows_connector.tray" not in tray_cmd:
            return
        data=json.loads(STATUS_FILE.read_text(encoding="utf-8")) if STATUS_FILE.exists() else {}
        node_pid=int(data.get("pid") or 0) if isinstance(data,dict) else 0
        if node_pid <= 0 or node_pid == os.getpid():
            return
        node=psutil.Process(node_pid)
        node_cmd=" ".join(node.cmdline()).lower()
        if "gpt_windows_connector.node" in node_cmd and "--configure" not in node_cmd:
            node.terminate()
    except Exception:
        pass

def configure_gui(existing: dict[str, object]) -> dict[str, object] | None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        from PIL import Image, ImageTk
    except Exception as exc:
        raise RuntimeError(f"Lucas configuration UI is unavailable: {exc}") from exc

    language = system_language()
    T = lambda zh, en: tr(zh, en, language)
    NAV_EN = {"常规":"General","安全":"Security","用户与权限":"Users & Permissions","文件访问":"File Access","网络":"Network","规则":"Rules","任务记录":"Task History","系统访问":"System Access"}
    C = {
        "window":"#FFFFFF","sidebar":"#F3F3F3","sidebar_hover":"#EAEAEA","card":"#FFFFFF",
        "line":"#E5E5E5","text":"#1F1F1F","muted":"#6B6B6B","subtle":"#8A8A8A",
        "control":"#F5F5F5","control_hover":"#ECECEC","blue":"#0F8CE9","blue_dark":"#0877C9",
        "green":"#107C10","orange":"#C45F00","red":"#C42B1C","white":"#FFFFFF",
    }
    FONT = "Segoe UI"
    root = tk.Tk()
    root.title(T("Lucas 设置", "Lucas Settings"))
    width,height=1180,780
    screen_w,screen_h=root.winfo_screenwidth(),root.winfo_screenheight()
    x=max((screen_w-width)//2,0); y=max((screen_h-height)//2,0)
    root.geometry(f"{width}x{height}+{x}+{y}")
    root.minsize(980, 680)
    root.configure(bg=C["window"])
    window_icon_image=None
    try:
        icon=Image.open(Path(__file__).with_name("assets")/"lucas-logo-square.png").convert("RGBA")
        icon.thumbnail((64,64),Image.Resampling.LANCZOS)
        window_icon_image=ImageTk.PhotoImage(icon)
        root.iconphoto(True,window_icon_image)
    except Exception:
        pass

    style = ttk.Style(root)
    try: style.theme_use("vista")
    except tk.TclError: pass
    style.configure("Lucas.TCombobox", font=(FONT,10), padding=6)

    gateway = tk.StringVar(value=str(existing.get("gateway_ws_url") or DEFAULT_GATEWAY))
    node_id = tk.StringVar(value=str(existing.get("node_id") or _default_node_id()))
    node_name = tk.StringVar(value=str(os.environ.get("COMPUTERNAME") or socket.gethostname()))
    roots = [str(x) for x in existing.get("allowed_roots",[]) if str(x).strip()] or [str(Path.home().resolve())]
    raw_connection_code = str(existing.get("connection_code") or "").strip()
    if len(raw_connection_code) != 8 or not raw_connection_code.isdigit(): raw_connection_code=f"{secrets.randbelow(100_000_000):08d}"
    connection_code = tk.StringVar(value=raw_connection_code)
    access_store = LocalAccessStore(ACCESS_FILE)
    security = dict(existing.get("security") or {}) if isinstance(existing.get("security"),dict) else {}
    approval = dict(security.get("approval_policy") or {}) if isinstance(security.get("approval_policy"),dict) else {}

    remember_approvals = tk.BooleanVar(value=bool(security.get("remember_approvals",True)))
    block_silent_network = tk.BooleanVar(value=bool(security.get("block_silent_network",True)))
    show_rule_summary = tk.BooleanVar(value=bool(security.get("show_rule_summary",True)))
    network_external = tk.StringVar(value=str(security.get("network_external") or "ask"))
    network_lan = tk.StringVar(value=str(security.get("network_lan") or "allow"))
    allowed_domains = tk.StringVar(value=", ".join(str(v) for v in (security.get("allowed_domains") or [])))
    rules_initial = str(security.get("rules_text") or "所有安全策略以本机设置为准；网页端只能查看，不能修改本机权限与允许目录。")
    approval_vars = {
        "system_info":tk.StringVar(value=str(approval.get("system_info") or "allow")),
        "shell":tk.StringVar(value=str(approval.get("shell") or "allow")),
        "file_write":tk.StringVar(value=str(approval.get("file_write") or "ask")),
        "file_delete":tk.StringVar(value=str(approval.get("file_delete") or "ask")),
        "service_control":tk.StringVar(value=str(approval.get("service_control") or "ask")),
        "process_control":tk.StringVar(value=str(approval.get("process_control") or "ask")),
        "desktop_control":tk.StringVar(value=str(approval.get("desktop_control") or "ask")),
        "screenshots":tk.StringVar(value=str(approval.get("screenshots") or "allow")),
        "clipboard":tk.StringVar(value=str(approval.get("clipboard") or "ask")),
        "browser_control":tk.StringVar(value=str(approval.get("browser_control") or "ask")),
        "browser_transfer":tk.StringVar(value=str(approval.get("browser_transfer") or "always_ask")),
        "git_write":tk.StringVar(value=str(approval.get("git_write") or "ask")),
        "git_push":tk.StringVar(value=str(approval.get("git_push") or "always_ask")),
        "software_install":tk.StringVar(value=str(approval.get("software_install") or "always_ask")),
        "registry_system":tk.StringVar(value=str(approval.get("registry_system") or "always_ask")),
        "high_risk":tk.StringVar(value=str(approval.get("high_risk") or "always_ask")),
    }
    try: is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception: is_admin = False

    shell = tk.Frame(root,bg=C["window"]); shell.pack(fill="both",expand=True)
    sidebar = tk.Frame(shell,bg=C["sidebar"],width=235); sidebar.pack(side="left",fill="y"); sidebar.pack_propagate(False)
    main = tk.Frame(shell,bg=C["window"]); main.pack(side="left",fill="both",expand=True)

    brand = tk.Frame(sidebar,bg=C["sidebar"]); brand.pack(fill="x",padx=18,pady=(20,16))
    brand_logo_image=None
    try:
        logo=Image.open(Path(__file__).with_name("assets")/"lucas-logo-horizontal.png").convert("RGBA")
        logo.thumbnail((180,66),Image.Resampling.LANCZOS)
        brand_logo_image=ImageTk.PhotoImage(logo)
        tk.Label(brand,image=brand_logo_image,bg=C["sidebar"],bd=0).pack(side="left")
    except Exception:
        tk.Label(brand,text="Lucas",font=(FONT,15,"bold"),fg=C["text"],bg=C["sidebar"]).pack(side="left")
    search = tk.Entry(sidebar,font=(FONT,10),bg="#E9E9E9",fg=C["subtle"],relief="flat",bd=0)
    search.insert(0,"搜索设置..."); search.pack(fill="x",padx=14,ipady=8,pady=(0,18))

    nav_frame = tk.Frame(sidebar,bg=C["sidebar"]); nav_frame.pack(fill="x",padx=8)
    nav_buttons, pages = {}, {}
    header = tk.Frame(main,bg=C["window"]); header.pack(fill="x",padx=54,pady=(34,12))
    title = tk.StringVar(value="安全")
    subtitle = tk.StringVar(value="控制 AI 在这台电脑上可以执行的操作。安全设置只能在本机修改。")
    tk.Label(header,textvariable=title,font=(FONT,23,"bold"),fg=C["text"],bg=C["window"]).pack(anchor="w")
    tk.Label(header,textvariable=subtitle,font=(FONT,10),fg=C["muted"],bg=C["window"]).pack(anchor="w",pady=(5,0))
    page_host = tk.Frame(main,bg=C["window"]); page_host.pack(fill="both",expand=True,padx=54,pady=(0,8))

    active_scroll_canvas=None
    def _mousewheel(event):
        if active_scroll_canvas is None or not active_scroll_canvas.winfo_exists(): return
        delta=int(-1*(event.delta/120)) if event.delta else 0
        if delta: active_scroll_canvas.yview_scroll(delta,"units")
    root.bind_all("<MouseWheel>",_mousewheel,add="+")

    def scroll_page():
        wrapper=tk.Frame(page_host,bg=C["window"]); canvas=tk.Canvas(wrapper,bg=C["window"],highlightthickness=0,bd=0)
        sb=ttk.Scrollbar(wrapper,orient="vertical",command=canvas.yview); body=tk.Frame(canvas,bg=C["window"])
        win=canvas.create_window((0,0),window=body,anchor="nw")
        body.bind("<Configure>",lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda e: canvas.itemconfigure(win,width=e.width))
        canvas.configure(yscrollcommand=sb.set); canvas.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
        wrapper._lucas_canvas=canvas
        return wrapper,body

    def section(parent,text):
        tk.Label(parent,text=text,font=(FONT,12,"bold"),fg=C["text"],bg=C["window"]).pack(anchor="w",pady=(18,10))
    def card(parent):
        f=tk.Frame(parent,bg=C["card"],highlightthickness=1,highlightbackground=C["line"]); f.pack(fill="x",pady=(0,16)); return f
    def divider(parent):
        tk.Frame(parent,bg=C["line"],height=1).pack(fill="x",padx=18)
    def row(parent,heading,desc="",control_builder=None):
        r=tk.Frame(parent,bg=C["card"]); r.pack(fill="x",padx=18,pady=13)
        r.grid_columnconfigure(0,weight=1)
        copy=tk.Frame(r,bg=C["card"]); copy.grid(row=0,column=0,sticky="ew")
        tk.Label(copy,text=heading,font=(FONT,10,"bold"),fg=C["text"],bg=C["card"]).pack(anchor="w")
        if desc: tk.Label(copy,text=desc,font=(FONT,9),fg=C["muted"],bg=C["card"],wraplength=560,justify="left").pack(anchor="w",pady=(3,0))
        if control_builder is not None:
            slot=tk.Frame(r,bg=C["card"]); slot.grid(row=0,column=1,sticky="e",padx=(22,0))
            control=control_builder(slot)
            if control is not None and not control.winfo_manager(): control.pack(anchor="e")
        return r
    def button(parent,text,command,primary=False,danger=False):
        bg=C["blue"] if primary else C["control"]; fg=C["white"] if primary else (C["red"] if danger else C["text"])
        active=C["blue_dark"] if primary else C["control_hover"]
        return tk.Button(parent,text=text,command=command,font=(FONT,9),bg=bg,fg=fg,activebackground=active,activeforeground=fg,relief="flat",bd=0,padx=14,pady=7,cursor="hand2")
    def combo(parent,var,values,width=14):
        return ttk.Combobox(parent,textvariable=var,values=values,state="readonly",width=width,style="Lucas.TCombobox")
    def switch(parent,var):
        cv=tk.Canvas(parent,width=42,height=24,bg=C["card"],highlightthickness=0,bd=0,cursor="hand2")
        def paint(*_):
            cv.delete("all"); on=bool(var.get()); fill=C["blue"] if on else "#C7C7C7"
            cv.create_oval(1,2,21,22,fill=fill,outline=fill); cv.create_oval(20,2,40,22,fill=fill,outline=fill); cv.create_rectangle(11,2,30,22,fill=fill,outline=fill)
            x=29 if on else 11; cv.create_oval(x-8,4,x+8,20,fill="#FFFFFF",outline="#FFFFFF")
        cv.bind("<Button-1>",lambda e: var.set(not var.get())); var.trace_add("write",paint); paint(); return cv

    DT={"allow":"直接允许","ask":"需要确认","always_ask":"始终确认","block":"阻止"}
    def decision_control(parent,var):
        display=tk.StringVar(value=DT.get(var.get(),"需要确认")); c=combo(parent,display,list(DT.values()),12)
        syncing={"value":False}; reverse={v:k for k,v in DT.items()}
        def display_to_policy(*_):
            if syncing["value"]: return
            value=reverse.get(display.get(),"ask")
            if var.get()==value: return
            syncing["value"]=True
            try: var.set(value)
            finally: syncing["value"]=False
        def policy_to_display(*_):
            if syncing["value"]: return
            value=DT.get(var.get(),"需要确认")
            if display.get()==value: return
            syncing["value"]=True
            try: display.set(value)
            finally: syncing["value"]=False
        display.trace_add("write",display_to_policy); var.trace_add("write",policy_to_display)
        return c

    wrap,body=scroll_page(); pages["常规"]=wrap
    section(body,"电脑"); c=card(body)
    row(c,"电脑名称","Windows 设备名称，只读。网页中的显示名称可单独修改。",lambda p: tk.Label(p,textvariable=node_name,font=(FONT,10),fg=C["muted"],bg=C["card"])); divider(c)
    row(c,"Node ID","设备唯一标识。",lambda p: tk.Label(p,textvariable=node_id,font=(FONT,9),fg=C["muted"],bg=C["card"]))
    section(body,"连接"); c=card(body)
    row(c,"Gateway","安全 WebSocket 地址。",lambda p: tk.Entry(p,textvariable=gateway,font=(FONT,10),relief="flat",bg=C["control"],fg=C["text"],bd=0,width=38)); divider(c)
    connection_status=tk.StringVar(value=T("检测中…", "Checking…")); connection_status_label=None
    def build_connection_status(p):
        nonlocal connection_status_label
        connection_status_label=tk.Label(p,textvariable=connection_status,font=(FONT,9,"bold"),fg=C["muted"],bg=C["card"]); return connection_status_label
    row(c,"连接状态","实时显示 Lucas Node 与 Gateway 的连接状态。",build_connection_status); divider(c)
    def refresh_connection_status():
        status_data={}
        try:
            loaded=json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded,dict): status_data=loaded
        except (OSError,json.JSONDecodeError): pass
        value=str(status_data.get("status") or "").strip(); detail=str(status_data.get("detail") or "").strip().lower()
        if value == "Online": text,color=T("已连接","Connected"),C["green"]
        elif value == "Connecting": text,color=T("正在连接…","Connecting…"),C["orange"]
        elif value == "Reconnecting": text,color=T("正在重新连接…","Reconnecting…"),C["orange"]
        elif value in {"Disconnected","Offline"}: text,color=T("未连接","Disconnected"),C["muted"]
        elif "token" in detail: text,color=T("设备认证失败","Device authentication failed"),C["red"]
        else: text,color=T("等待连接","Waiting for connection"),C["muted"]
        connection_status.set(text); connection_status_label.configure(fg=color)
        try: root.after(1000,refresh_connection_status)
        except tk.TclError: pass

    def regenerate_connection_code():
        new_code=f"{secrets.randbelow(100_000_000):08d}"
        connection_code.set(new_code)
        latest=dict(existing); latest["connection_code"]=new_code
        _save_config(latest); _restart_node_for_apply()
    def build_connection_code(p):
        f=tk.Frame(p,bg=C["card"]); tk.Label(f,textvariable=connection_code,font=(FONT,14,"bold"),fg=C["blue"],bg=C["card"]).pack(side="left"); button(f,"重新生成",regenerate_connection_code).pack(side="left",padx=(10,0)); return f
    row(c,"连接码","新 Lucas 账号首次连接时需要 Node ID + 这组 8 位连接码；连接码正确后仍必须由本机批准账号。",build_connection_code)

    section(body,"Lucas Node"); c=card(body)
    current_version=_app_version(); version_status=tk.StringVar(value=f"当前版本 {current_version} · 正在检查更新…"); update_button=None; update_control=None
    def run_update():
        if not messagebox.askyesno("Lucas","更新 Lucas Node？现有 Node ID、用户权限、Allowed Folders 和安全设置会保留。"): return
        try:
            version_status.set("正在启动更新…")
            if update_button is not None: update_button.configure(state="disabled")
            script_path=Path(tempfile.gettempdir())/"Lucas-Node-update.ps1"
            request=urllib.request.Request(f"{INSTALLER_URL}?t={int(time.time())}",headers={"Cache-Control":"no-cache","Pragma":"no-cache","User-Agent":"Lucas-Node-Updater"})
            with urllib.request.urlopen(request,timeout=15) as response: script_path.write_bytes(response.read())
            subprocess.Popen(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(script_path)],creationflags=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)); root.after(300,root.destroy)
        except Exception as exc:
            version_status.set(f"更新启动失败：{exc}")
            if update_button is not None: update_button.configure(state="normal")
            messagebox.showerror("Lucas",f"无法启动更新：{exc}")
    def build_update_control(p):
        nonlocal update_button,update_control
        update_control=tk.Frame(p,bg=C["card"]); tk.Label(update_control,textvariable=version_status,font=(FONT,9,"bold"),fg=C["muted"],bg=C["card"]).pack(side="left"); update_button=button(update_control,"更新 Node",run_update); return update_control
    row(c,"Lucas Node","自动检查新版本；仅检测到新版时显示更新按钮。",build_update_control)
    def check_update_worker():
        latest=_fetch_latest_version()
        def apply_result():
            if update_button is not None: update_button.pack_forget()
            if not latest: version_status.set(f"当前版本 {current_version} · 无法检查更新"); return
            if current_version != "dev" and _version_key(latest)>_version_key(current_version):
                version_status.set(f"新版本 {latest} 可用")
                if update_button is not None: update_button.configure(state="normal"); update_button.pack(side="left",padx=(10,0))
            else: version_status.set(f"当前版本 {current_version} · 已是最新版本")
        try: root.after(0,apply_result)
        except tk.TclError: pass
    threading.Thread(target=check_update_worker,daemon=True).start()

    wrap,body=scroll_page(); pages["安全"]=wrap
    section(body,"权限"); c=card(body); preset_syncing={"value":False}
    preset_display=tk.StringVar(value=detect_security_preset({k:v.get() for k,v in approval_vars.items()},network_external.get(),network_lan.get(),block_silent_network.get(),[v.strip() for v in allowed_domains.get().replace(";",",").split(",") if v.strip()])); preset_desc=tk.StringVar(value=PRESET_DESCRIPTIONS[preset_display.get()])
    def sync_preset_from_fields(*_):
        if preset_syncing["value"]: return
        name=detect_security_preset({k:v.get() for k,v in approval_vars.items()},network_external.get(),network_lan.get(),block_silent_network.get(),[v.strip() for v in allowed_domains.get().replace(";",",").split(",") if v.strip()]); preset_syncing["value"]=True; preset_display.set(name); preset_desc.set(PRESET_DESCRIPTIONS[name]); preset_syncing["value"]=False
    def apply_preset(*_):
        if preset_syncing["value"]: return
        name=preset_display.get(); preset_desc.set(PRESET_DESCRIPTIONS.get(name,PRESET_DESCRIPTIONS["自定义"])); preset=PRESETS.get(name)
        if not preset: return
        preset_syncing["value"]=True
        for k,v in preset["approval_policy"].items(): approval_vars[k].set(str(v))
        network_external.set(str(preset["network_external"])); network_lan.set(str(preset["network_lan"])); block_silent_network.set(bool(preset["block_silent_network"]));
        if name == "完全访问权限": allowed_domains.set("")
        preset_syncing["value"]=False
    preset_display.trace_add("write",apply_preset)
    for var in [network_external,network_lan,allowed_domains,block_silent_network,*approval_vars.values()]: var.trace_add("write",sync_preset_from_fields)
    def preset_control(p):
        f=tk.Frame(p,bg=C["card"]); combo(f,preset_display,["请求批准（Recommended）","帮我批准","完全访问权限","自定义"],24).pack(anchor="e"); tk.Label(f,textvariable=preset_desc,font=(FONT,8),fg=C["muted"],bg=C["card"],wraplength=290,justify="right").pack(anchor="e",pady=(4,0)); return f
    row(c,"快捷设置","选择预设后会立即同步下方审批策略与网络策略；手动修改任一项后自动变为“自定义”。",preset_control); divider(c); row(c,"权限来源","所有安全权限仅可在本机修改；网页只能查看。",lambda p: tk.Label(p,text="仅本机",font=(FONT,9,"bold"),fg=C["blue"],bg=C["card"]))
    section(body,"审批策略"); c=card(body)
    prs=[("system_info","系统信息读取","读取进程、窗口、系统状态及项目只读信息。"),("shell","普通 PowerShell / 命令行","运行不属于高风险分类的普通命令。"),("file_write","文件写入与修改","创建、编辑、移动或复制文件。"),("file_delete","文件删除","删除已授权目录中的文件或文件夹。"),("process_control","进程启动 / 停止","启动程序、终止 Lucas 管理的进程或控制进程生命周期。"),("service_control","Windows 服务启动 / 停止","启动、停止、重启或修改 Windows 服务。"),("registry_system","注册表与系统配置","修改注册表、系统配置、电源、账户及受保护系统设置。"),("software_install","安装 / 卸载软件","安装包管理器、MSI、winget、Chocolatey 或卸载软件。"),("desktop_control","电脑操控","鼠标、键盘、窗口激活、输入、点击、滚动和 UI 自动化。"),("screenshots","屏幕截图","读取当前屏幕内容用于 Computer Use。"),("clipboard","剪贴板","读取或写入 Windows 剪贴板。"),("browser_control","浏览器操控","打开页面、点击、输入、选择和浏览器自动化。"),("browser_transfer","浏览器上传 / 下载","上传本地文件或下载文件到允许目录。"),("git_write","Git 本地修改","add、commit、切换/创建分支等本地仓库写操作。"),("git_push","Git Push / 远程写入","向远端仓库推送代码或其他远程写操作。"),("high_risk","其他高风险系统修改","磁盘、账户、安全软件、关机重启等高风险操作。")]
    for i,(k,h,d) in enumerate(prs):
        row(c,h,d,lambda p,k=k: decision_control(p,approval_vars[k]));
        if i<len(prs)-1: divider(c)
    divider(c); row(c,"记住本次会话已批准操作","只记住完全相同操作；Lucas 重启后自动清除。",lambda p: switch(p,remember_approvals))

    wrap,body=scroll_page(); pages["用户与权限"]=wrap
    section(body,"已授权 Lucas 用户"); users_card=card(body)
    tk.Label(users_card,text="只有在这台电脑上批准过的 Lucas 用户才能操作此 Node。权限和目录以这里的本地设置为最终准则。",font=(FONT,9),fg=C["muted"],bg=C["card"],wraplength=680,justify="left").pack(anchor="w",padx=18,pady=(14,10))
    users_shell=tk.Frame(users_card,bg=C["card"]); users_shell.pack(fill="both",expand=True,padx=18,pady=(0,14))
    user_list=tk.Listbox(users_shell,width=34,height=13,font=(FONT,9),bg=C["control"],fg=C["text"],relief="flat",bd=0,highlightthickness=1,highlightbackground=C["line"],selectbackground="#DCEEFF",selectforeground=C["text"]); user_list.pack(side="left",fill="y")
    user_editor=tk.Frame(users_shell,bg=C["card"]); user_editor.pack(side="left",fill="both",expand=True,padx=(18,0))
    selected_user_id={"value":""}; user_records=[]
    user_identity=tk.StringVar(value="选择一个用户"); user_preset=tk.StringVar(value="请求批准（Recommended）")
    preset_to_id={"请求批准（Recommended）":"request_approval","帮我批准":"auto_approve","完全访问权限":"full_access","自定义":"custom"}; id_to_preset={v:k for k,v in preset_to_id.items()}
    tk.Label(user_editor,textvariable=user_identity,font=(FONT,11,"bold"),fg=C["text"],bg=C["card"]).pack(anchor="w",pady=(2,12))
    perm_row=tk.Frame(user_editor,bg=C["card"]); perm_row.pack(fill="x",pady=(0,10)); tk.Label(perm_row,text="快捷权限",font=(FONT,9,"bold"),fg=C["text"],bg=C["card"]).pack(side="left"); combo(perm_row,user_preset,list(preset_to_id),24).pack(side="right")
    tk.Label(user_editor,text="允许访问的文件夹",font=(FONT,9,"bold"),fg=C["text"],bg=C["card"]).pack(anchor="w")
    user_roots=tk.Listbox(user_editor,selectmode="multiple",height=7,font=(FONT,9),bg=C["control"],fg=C["text"],relief="flat",bd=0,highlightthickness=1,highlightbackground=C["line"],selectbackground="#DCEEFF",selectforeground=C["text"]); user_roots.pack(fill="x",pady=(5,10))
    for item in roots: user_roots.insert("end",item)
    user_note=tk.StringVar(value="快捷权限决定默认审批策略；文件夹始终受 Node Allowed Folders 硬边界限制。详细权限可单独修改。"); tk.Label(user_editor,textvariable=user_note,font=(FONT,8),fg=C["muted"],bg=C["card"],wraplength=430,justify="left").pack(anchor="w")
    user_actions=tk.Frame(user_editor,bg=C["card"]); user_actions.pack(fill="x",pady=(14,0))

    def refresh_users(select_id=None):
        nonlocal user_records
        user_records=access_store.list_users(); user_list.delete(0,"end")
        target=None
        for idx,record in enumerate(user_records):
            label=str(record.get("name") or record.get("email") or record.get("user_id") or "未知用户")
            preset_value=id_to_preset.get(normalize_preset(str(record.get("preset") or ("full_access" if record.get("permission_level")=="admin" else "request_approval"))),"请求批准（Recommended）")
            user_list.insert("end",f"{label}   [{preset_value}]")
            if select_id and str(record.get("user_id"))==str(select_id): target=idx
        if user_records:
            index=target if target is not None else 0; user_list.selection_clear(0,"end"); user_list.selection_set(index); user_list.activate(index); load_user()
        else:
            selected_user_id["value"]=""; user_identity.set("暂无已授权用户"); user_preset.set("请求批准（Recommended）"); user_roots.selection_clear(0,"end")

    def load_user(*_):
        sel=user_list.curselection()
        if not sel or sel[0]>=len(user_records): return
        record=user_records[sel[0]]; selected_user_id["value"]=str(record.get("user_id") or "")
        name=str(record.get("name") or record.get("email") or selected_user_id["value"]); email=str(record.get("email") or "")
        user_identity.set(name + (f"  ·  {email}" if email and email!=name else "")); user_preset.set(id_to_preset.get(normalize_preset(str(record.get("preset") or ("full_access" if record.get("permission_level")=="admin" else "request_approval"))),"请求批准（Recommended）"))
        user_roots.selection_clear(0,"end"); granted={str(Path(v).expanduser().resolve()) for v in (record.get("allowed_roots") or [])}
        for idx,path in enumerate(roots):
            try: resolved=str(Path(path).expanduser().resolve())
            except Exception: resolved=path
            if resolved in granted: user_roots.selection_set(idx)
    user_list.bind("<<ListboxSelect>>",load_user)

    def save_user_access():
        uid=selected_user_id["value"]
        if not uid: return
        record=next((r for r in user_records if str(r.get("user_id"))==uid),None)
        if not record: return
        selected=[roots[i] for i in user_roots.curselection()]; selected=clamp_roots(selected,roots)
        if not selected: messagebox.showerror("Lucas","请至少为该用户选择一个允许访问的文件夹。"); return
        preset=preset_to_id.get(user_preset.get(),"request_approval")
        existing_security=record.get("security") if isinstance(record.get("security"),dict) else None
        security=existing_security if preset=="custom" and existing_security else preset_security(preset)
        access_store.upsert({"user_id":uid,"name":record.get("name"),"email":record.get("email")},preset,selected,security=security,enabled=True)
        user_note.set("已保存。快捷权限和文件夹会在该用户下一次操作时立即生效。"); refresh_users(uid)

    def revoke_user_access():
        uid=selected_user_id["value"]
        if not uid: return
        record=next((r for r in user_records if str(r.get("user_id"))==uid),None); label=str((record or {}).get("name") or (record or {}).get("email") or uid)
        if not messagebox.askyesno("Lucas",f"撤销 {label} 对这台电脑的访问权限？\n\n撤销后，该用户必须重新在本机获得批准。"): return
        access_store.remove(uid); user_note.set("已撤销访问。"); refresh_users()
    def edit_user_details():
        uid=selected_user_id["value"]
        if not uid: return
        record=next((r for r in user_records if str(r.get("user_id"))==uid),None)
        if not record: return
        selected=[roots[i] for i in user_roots.curselection()] or list(record.get("allowed_roots") or [])
        selected=clamp_roots(selected,roots)
        if not selected: messagebox.showerror("Lucas","请先为该用户选择至少一个允许访问的文件夹。"); return
        preset=preset_to_id.get(user_preset.get(),normalize_preset(str(record.get("preset") or "request_approval")))
        security=dict(record.get("security") or preset_security(preset))
        policy=dict(security.get("approval_policy") or {})
        win=tk.Toplevel(root); win.title("Lucas · 用户详细权限"); win.geometry("720x720"); win.transient(root); win.grab_set()
        outer=tk.Frame(win,bg=C["window"]); outer.pack(fill="both",expand=True,padx=22,pady=18)
        tk.Label(outer,text="详细权限",font=(FONT,16,"bold"),fg=C["text"],bg=C["window"]).pack(anchor="w")
        tk.Label(outer,text=user_identity.get(),font=(FONT,9),fg=C["muted"],bg=C["window"]).pack(anchor="w",pady=(3,12))
        canvas=tk.Canvas(outer,bg=C["window"],highlightthickness=0); sb=ttk.Scrollbar(outer,orient="vertical",command=canvas.yview); body=tk.Frame(canvas,bg=C["window"]); holder=canvas.create_window((0,0),window=body,anchor="nw"); canvas.configure(yscrollcommand=sb.set); canvas.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y"); body.bind("<Configure>",lambda e: canvas.configure(scrollregion=canvas.bbox("all"))); canvas.bind("<Configure>",lambda e: canvas.itemconfigure(holder,width=e.width))
        labels={"system_info":"系统信息读取","shell":"普通 PowerShell / 命令行","file_write":"文件写入与修改","file_delete":"文件删除","process_control":"进程启动 / 停止","service_control":"Windows 服务","registry_system":"注册表与系统配置","software_install":"安装 / 卸载软件","desktop_control":"电脑操控","screenshots":"屏幕截图","clipboard":"剪贴板","browser_control":"浏览器操控","browser_transfer":"浏览器上传 / 下载","git_write":"Git 本地修改","git_push":"Git Push / 远程写入","high_risk":"其他高风险系统修改"}
        detail_vars={}
        for key in APPROVAL_DEFAULTS:
            line=tk.Frame(body,bg=C["card"],highlightthickness=1,highlightbackground=C["line"]); line.pack(fill="x",pady=(0,6)); tk.Label(line,text=labels.get(key,key),font=(FONT,9,"bold"),fg=C["text"],bg=C["card"]).pack(side="left",padx=12,pady=10); var=tk.StringVar(value=str(policy.get(key) or APPROVAL_DEFAULTS[key])); detail_vars[key]=var; combo(line,var,["allow","ask","always_ask","block"],14).pack(side="right",padx=12,pady=6)
        ext=tk.StringVar(value=str(security.get("network_external") or "ask")); lan=tk.StringVar(value=str(security.get("network_lan") or "allow"))
        for title,var in (("外部网络访问",ext),("本地局域网访问",lan)):
            line=tk.Frame(body,bg=C["card"],highlightthickness=1,highlightbackground=C["line"]); line.pack(fill="x",pady=(0,6)); tk.Label(line,text=title,font=(FONT,9,"bold"),fg=C["text"],bg=C["card"]).pack(side="left",padx=12,pady=10); combo(line,var,["allow","ask","always_ask","block"],14).pack(side="right",padx=12,pady=6)
        footer=tk.Frame(win,bg=C["window"]); footer.pack(fill="x",padx=22,pady=(0,18))
        def save_details():
            custom=dict(security); custom["approval_policy"]={k:v.get() for k,v in detail_vars.items()}; custom["network_external"]=ext.get(); custom["network_lan"]=lan.get()
            access_store.upsert({"user_id":uid,"name":record.get("name"),"email":record.get("email")},"custom",selected,security=custom,enabled=True); user_note.set("详细权限已保存，该用户下一次操作立即生效。"); win.destroy(); refresh_users(uid)
        button(footer,"保存详细权限",save_details,primary=True).pack(side="right"); button(footer,"取消",win.destroy).pack(side="right",padx=(0,8))

    button(user_actions,"保存权限",save_user_access,primary=True).pack(side="right"); button(user_actions,"详细权限",edit_user_details).pack(side="right",padx=(0,8)); button(user_actions,"撤销访问",revoke_user_access,danger=True).pack(side="right",padx=(0,8)); button(user_actions,"刷新",lambda: refresh_users(selected_user_id["value"])).pack(side="right",padx=(0,8))
    refresh_users()
    c=card(body); row(c,"本地最终授权","VPS 只负责转发用户身份和请求。是否允许执行、实际权限和允许目录都由此 Windows Node 再次检查。",lambda p: tk.Label(p,text="已启用",font=(FONT,9,"bold"),fg=C["green"],bg=C["card"]))

    wrap,body=scroll_page(); pages["文件访问"]=wrap
    section(body,"沙箱与文件访问"); c=card(body); tk.Label(c,text="仅允许访问以下文件夹",font=(FONT,10,"bold"),fg=C["text"],bg=C["card"]).pack(anchor="w",padx=18,pady=(16,4)); tk.Label(c,text="文件读写、上传、下载与项目工作区都受此列表限制。",font=(FONT,9),fg=C["muted"],bg=C["card"]).pack(anchor="w",padx=18,pady=(0,10)); lw=tk.Frame(c,bg=C["card"]); lw.pack(fill="both",padx=18,pady=(0,16)); roots_list=tk.Listbox(lw,height=9,font=(FONT,10),bg=C["control"],fg=C["text"],relief="flat",bd=0,highlightthickness=1,highlightbackground=C["line"],selectbackground="#DCEEFF",selectforeground=C["text"]); roots_list.pack(side="left",fill="both",expand=True)
    for item in roots: roots_list.insert("end",item)
    acts=tk.Frame(lw,bg=C["card"]); acts.pack(side="left",fill="y",padx=(10,0))
    def add_root():
        p=filedialog.askdirectory(title="选择 Lucas 可以访问的文件夹")
        if p and p not in roots_list.get(0,"end"): roots_list.insert("end",p)
    def remove_root():
        sel=roots_list.curselection()
        if sel: roots_list.delete(sel[0])
    button(acts,"添加文件夹",add_root,primary=True).pack(fill="x",pady=(0,8)); button(acts,"移除",remove_root,danger=True).pack(fill="x"); c=card(body); row(c,"硬边界","不允许通过 shell、浏览器上传/下载、进程启动或路径参数绕过 Allowed Folders。",lambda p: tk.Label(p,text="已启用",font=(FONT,9,"bold"),fg=C["green"],bg=C["card"]))

    wrap,body=scroll_page(); pages["网络"]=wrap
    section(body,"网络访问"); c=card(body); row(c,"外部网络访问","访问互联网、远程 API、Git 远端等。",lambda p: decision_control(p,network_external)); divider(c); row(c,"本地局域网访问","localhost、私有 IP 与 .local 地址。",lambda p: decision_control(p,network_lan)); divider(c); row(c,"允许的域名","可选，逗号分隔；为空表示不额外限制域名。支持 *.example.com。",lambda p: tk.Entry(p,textvariable=allowed_domains,font=(FONT,10),relief="flat",bg=C["control"],fg=C["text"],bd=0,width=40)); divider(c); row(c,"阻止后台静默联网","无法识别目标地址的网络命令必须在本机确认。",lambda p: switch(p,block_silent_network))

    wrap,body=scroll_page(); pages["规则"]=wrap
    section(body,"本地 Rules"); c=card(body); tk.Label(c,text="本地安全规则",font=(FONT,10,"bold"),fg=C["text"],bg=C["card"]).pack(anchor="w",padx=18,pady=(16,4)); tk.Label(c,text="需要确认的操作会把规则摘要一起显示在本机审批窗口。",font=(FONT,9),fg=C["muted"],bg=C["card"]).pack(anchor="w",padx=18,pady=(0,10)); rules_text=tk.Text(c,height=8,font=(FONT,10),bg=C["control"],fg=C["text"],relief="flat",bd=0,wrap="word",padx=10,pady=9); rules_text.insert("1.0",rules_initial); rules_text.pack(fill="x",padx=18,pady=(0,14)); divider(c); row(c,"执行前显示规则摘要","审批时显示本地规则。",lambda p: switch(p,show_rule_summary))

    tasks_wrapper,tasks_body=scroll_page(); pages["任务记录"]=tasks_wrapper
    section(tasks_body,"任务记录")
    task_card=card(tasks_body)
    tk.Label(task_card,text="记录本机通过 Lucas 执行的大任务与小任务耗时。5 分钟无新操作后自动结束一个大任务。",font=(FONT,9),fg=C["muted"],bg=C["card"],wraplength=650,justify="left").pack(anchor="w",padx=18,pady=(14,10))
    task_list=tk.Frame(task_card,bg=C["card"]); task_list.pack(fill="both",expand=True,padx=18,pady=(0,14))
    def _duration_text(ms):
        sec=max(0,int((ms or 0)/1000)); h,rem=divmod(sec,3600); m,s=divmod(rem,60)
        return f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s")
    def refresh_local_tasks():
        for child in task_list.winfo_children(): child.destroy()
        try: runs=TaskRunStore(TASK_RUNS_FILE).list_runs("local",node_id=node_id.get().strip() or None,limit=100)
        except Exception as exc:
            tk.Label(task_list,text=f"无法读取任务记录：{exc}",font=(FONT,9),fg=C["red"],bg=C["card"]).pack(anchor="w",pady=8); return
        if not runs:
            tk.Label(task_list,text="还没有任务记录。",font=(FONT,9),fg=C["muted"],bg=C["card"]).pack(anchor="w",pady=8); return
        for run in runs:
            box=tk.Frame(task_list,bg=C["control"],highlightthickness=1,highlightbackground=C["line"]); box.pack(fill="x",pady=(0,8))
            head=tk.Frame(box,bg=C["control"]); head.pack(fill="x",padx=12,pady=(10,6))
            tk.Label(head,text=str(run.get("title") or "Lucas task"),font=(FONT,9,"bold"),fg=C["text"],bg=C["control"]).pack(side="left")
            tk.Label(head,text=f"{run.get('status','')} · {_duration_text(run.get('duration_ms'))}",font=(FONT,9),fg=C["muted"],bg=C["control"]).pack(side="right")
            for step in run.get("steps",[])[:20]:
                row=tk.Frame(box,bg=C["control"]); row.pack(fill="x",padx=18,pady=2)
                tk.Label(row,text=str(step.get("action") or "operation"),font=(FONT,8),fg=C["text"],bg=C["control"]).pack(side="left")
                tk.Label(row,text=_duration_text(step.get("duration_ms")),font=(FONT,8),fg=C["muted"],bg=C["control"]).pack(side="right")
    button(task_card,"刷新",refresh_local_tasks).pack(anchor="e",padx=18,pady=(0,14))
    refresh_local_tasks()

    wrap,body=scroll_page(); pages["系统访问"]=wrap
    section(body,"Windows 权限"); c=card(body); row(c,"当前 Windows 权限","Lucas 应用权限与 Windows 管理员权限是两层独立控制。",lambda p: tk.Label(p,text=("管理员" if is_admin else "标准用户"),font=(FONT,10,"bold"),fg=(C["green"] if is_admin else C["orange"]),bg=C["card"])); divider(c); row(c,"Elevated / Admin",("当前进程已提升，可以执行 Windows 允许的管理员操作。" if is_admin else "服务、受保护注册表、驱动及部分硬件控制可能需要 Windows 管理员权限。"),lambda p: tk.Label(p,text=("已启用" if is_admin else "未启用"),font=(FONT,9,"bold"),fg=(C["green"] if is_admin else C["muted"]),bg=C["card"])); c=card(body); row(c,"重要","Full Access 不会自动提升 Windows 权限；Windows UAC 仍是最终系统边界。")

    desc={"常规":"连接身份与此电脑的 Lucas 基础配置。","安全":"控制 AI 在这台电脑上可以执行的操作。安全设置只能在本机修改。","用户与权限":"管理哪些 Lucas 用户可以操作此电脑，以及每个用户的权限和允许目录。","文件访问":"使用 Allowed Folders 建立文件与工作区的硬边界。","网络":"控制互联网、局域网、域名与后台网络请求。","规则":"管理本机审批时展示的安全规则。","任务记录":"查看本机 Lucas 大任务与小任务执行时间。","系统访问":"查看 Lucas 与 Windows 管理员权限的实际状态。"}
    def show_page(name):
        nonlocal active_scroll_canvas
        if name not in pages: name="常规"
        for p in pages.values(): p.pack_forget()
        pages[name].pack(fill="both",expand=True); active_scroll_canvas=getattr(pages[name],"_lucas_canvas",None); title.set(name if language=="zh" else NAV_EN[name]); subtitle.set(desc[name] if language=="zh" else SETTINGS_EN.get(desc[name], desc[name])); _save_last_page(name)
        if active_scroll_canvas is not None: root.after_idle(lambda c=active_scroll_canvas: c.yview_moveto(0) if c.winfo_exists() else None)
        for k,b in nav_buttons.items(): b.configure(bg=("#E1E1E1" if k==name else C["sidebar"]),fg=C["text"])
    for name in ("常规","安全","用户与权限","文件访问","网络","规则","任务记录","系统访问"):
        b=tk.Button(nav_frame,text=(name if language=="zh" else NAV_EN[name]),command=lambda n=name: show_page(n),font=(FONT,10),fg=C["text"],bg=C["sidebar"],activebackground=C["sidebar_hover"],activeforeground=C["text"],relief="flat",bd=0,anchor="w",padx=14,pady=9,cursor="hand2"); b.pack(fill="x",pady=1); nav_buttons[name]=b
    sidebar_footer=tk.Frame(sidebar,bg=C["sidebar"]); sidebar_footer.pack(side="bottom",fill="x",padx=22,pady=20); tk.Label(sidebar_footer,text=f"Lucas v{_app_version()}",font=(FONT,8,"bold"),fg=C["muted"],bg=C["sidebar"]).pack(anchor="w"); tk.Label(sidebar_footer,text="安全策略仅在此电脑上生效",font=(FONT,8),fg=C["subtle"],bg=C["sidebar"]).pack(anchor="w",pady=(3,0))

    footer=tk.Frame(main,bg=C["window"],highlightthickness=1,highlightbackground=C["line"]); footer.pack(fill="x",side="bottom"); fi=tk.Frame(footer,bg=C["window"]); fi.pack(fill="x",padx=54,pady=12); save_feedback=tk.StringVar(value="安全设置仅在此电脑上生效"); tk.Label(fi,textvariable=save_feedback,font=(FONT,9),fg=C["muted"],bg=C["window"]).pack(side="left")

    result=None; save_button=None
    def reset_defaults():
        if not messagebox.askyesno("Lucas","恢复推荐的安全设置？Allowed Folders 不会被删除。"): return
        preset_display.set("请求批准（Recommended）")
        for k,v in APPROVAL_DEFAULTS.items(): approval_vars[k].set(v)
        remember_approvals.set(True); network_external.set("ask"); network_lan.set("allow"); allowed_domains.set(""); block_silent_network.set(True); show_rule_summary.set(True); rules_text.delete("1.0","end"); rules_text.insert("1.0","所有安全策略以本机设置为准；网页端只能查看，不能修改本机权限与允许目录。")
    def save():
        nonlocal result
        gv=gateway.get().strip(); rv=[str(Path(v).expanduser().resolve()) for v in roots_list.get(0,"end") if str(v).strip()]
        if not gv.startswith(("ws://","wss://")): messagebox.showerror("Lucas","Gateway 必须以 ws:// 或 wss:// 开头。"); return
        if not node_name.get().strip() or not node_id.get().strip(): messagebox.showerror("Lucas","电脑名称和 Node ID 不能为空。"); return
        if not rv or any(not Path(v).is_dir() for v in rv): messagebox.showerror("Lucas","Allowed Folders 中的每个目录都必须真实存在。"); return
        domains=[v.strip().lower() for v in allowed_domains.get().replace(";",",").split(",") if v.strip()]
        updated=dict(existing); updated.pop("pairing_code",None); updated.pop("permission_level",None); updated.update({"gateway_ws_url":gv.rstrip("/"),"node_name":str(os.environ.get("COMPUTERNAME") or socket.gethostname()),"node_id":node_id.get().strip(),"connection_code":connection_code.get().strip(),"allowed_roots":rv,"security":{"approval_policy":{k:v.get() for k,v in approval_vars.items()},"remember_approvals":remember_approvals.get(),"network_external":network_external.get(),"network_lan":network_lan.get(),"allowed_domains":domains,"block_silent_network":block_silent_network.get(),"rules_text":rules_text.get("1.0","end").strip(),"show_rule_summary":show_rule_summary.get()}}); updated.setdefault("launch_at_startup",True); updated.setdefault("connection_enabled",True)
        _save_config(updated); result=updated; _restart_node_for_apply(); save_feedback.set("已保存 · Lucas Node 正在应用新设置")
        if save_button is not None: save_button.configure(text="已保存")
        def reset_feedback():
            save_feedback.set("安全设置仅在此电脑上生效")
            if save_button is not None: save_button.configure(text="保存更改")
        root.after(1800,reset_feedback)

    save_button=button(fi,"保存更改",save,primary=True); save_button.pack(side="right"); button(fi,"恢复默认",reset_defaults).pack(side="right",padx=(0,10)); button(fi,"取消",root.destroy).pack(side="right",padx=(0,10))
    show_page(_load_last_page())
    localize_tk_tree(root, SETTINGS_EN, language)
    refresh_connection_status(); root.mainloop(); return result
