from __future__ import annotations

import ctypes
import json
import os
import re
import socket
import subprocess
import tempfile
import threading
import urllib.request
import uuid
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any

APP_NAME = "Lucas"
DEFAULT_GATEWAY = "wss://lucasmcp.com/ws/node"
CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "node-config.json"
STATE_FILE = CONFIG_DIR / "node-state.json"
STATUS_FILE = CONFIG_DIR / "node-status.json"
LATEST_VERSION_URL = "https://raw.githubusercontent.com/Neal86/Lucas/main/pyproject.toml"
INSTALLER_URL = "https://raw.githubusercontent.com/Neal86/Lucas/main/scripts/install-node.ps1"

APPROVAL_DEFAULTS = {
    "system_info":"allow","shell":"allow","file_write":"ask","file_delete":"ask",
    "service_control":"ask","process_control":"ask","desktop_control":"ask","screenshots":"allow",
    "clipboard":"ask","browser_control":"ask","browser_transfer":"always_ask","git_write":"ask",
    "git_push":"always_ask","software_install":"always_ask","registry_system":"always_ask","high_risk":"always_ask",
}
PRESETS = {
    "请求批准（Recommended）": {"permission_level":"operate","approval_policy":APPROVAL_DEFAULTS,"network_external":"ask","network_lan":"allow","block_silent_network":True},
    "帮我批准": {"permission_level":"operate","approval_policy":{**{k:"allow" for k in APPROVAL_DEFAULTS},"browser_transfer":"always_ask","git_push":"always_ask","software_install":"always_ask","registry_system":"always_ask","high_risk":"always_ask","service_control":"always_ask"},"network_external":"allow","network_lan":"allow","block_silent_network":False},
    "完全访问权限": {"permission_level":"admin","approval_policy":{k:"allow" for k in APPROVAL_DEFAULTS},"network_external":"allow","network_lan":"allow","block_silent_network":False},
}
PRESET_DESCRIPTIONS = {
    "请求批准（Recommended）":"编辑外部文件和使用互联网时始终询问。",
    "帮我批准":"仅对检测到的高风险操作请求批准。",
    "完全访问权限":"可不受限制地访问互联网和允许目录中的任何文件。",
    "自定义":"使用下方逐项设置。",
}

def detect_security_preset(permission_level: str, approval_policy: dict[str,str], network_external: str, network_lan: str, block_silent_network: bool) -> str:
    for name,preset in PRESETS.items():
        if permission_level != preset["permission_level"] or network_external != preset["network_external"] or network_lan != preset["network_lan"] or bool(block_silent_network) != bool(preset["block_silent_network"]):
            continue
        if all(str(approval_policy.get(k)) == str(v) for k,v in preset["approval_policy"].items()):
            return name
    return "自定义"

def _version_key(value: str) -> tuple[int,...]:
    return tuple(int(x) for x in re.findall(r"\d+", value)[:4]) or (0,)

def _fetch_latest_version(timeout: float = 5.0) -> str | None:
    try:
        with urllib.request.urlopen(LATEST_VERSION_URL, timeout=timeout) as response:
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
    machine = os.environ.get("COMPUTERNAME") or socket.gethostname() or "windows-node"
    return f"{machine}-{uuid.getnode():012x}".lower()

def _save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temp = CONFIG_FILE.with_name(f"{CONFIG_FILE.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(CONFIG_FILE)

def configure_gui(existing: dict[str, object]) -> dict[str, object] | None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except Exception as exc:
        raise RuntimeError(f"Lucas configuration UI is unavailable: {exc}") from exc

    C = {
        "window":"#FFFFFF","sidebar":"#F3F3F3","sidebar_hover":"#EAEAEA","card":"#FFFFFF",
        "line":"#E5E5E5","text":"#1F1F1F","muted":"#6B6B6B","subtle":"#8A8A8A",
        "control":"#F5F5F5","control_hover":"#ECECEC","blue":"#0F8CE9","blue_dark":"#0877C9",
        "green":"#107C10","orange":"#C45F00","red":"#C42B1C","white":"#FFFFFF",
    }
    FONT = "Segoe UI"
    root = tk.Tk()
    root.title("Lucas 设置")
    root.geometry("1180x780")
    root.minsize(980, 680)
    root.configure(bg=C["window"])

    style = ttk.Style(root)
    try: style.theme_use("vista")
    except tk.TclError: pass
    style.configure("Lucas.TCombobox", font=(FONT,10), padding=6)

    gateway = tk.StringVar(value=str(existing.get("gateway_ws_url") or DEFAULT_GATEWAY))
    node_id = tk.StringVar(value=str(existing.get("node_id") or _default_node_id()))
    node_name = tk.StringVar(value=str(os.environ.get("COMPUTERNAME") or socket.gethostname()))
    pairing_code = tk.StringVar(value=str(existing.get("pairing_code") or ""))
    permission = tk.StringVar(value=str(existing.get("permission_level") or "operate").lower())
    if permission.get() not in {"read","operate","admin"}: permission.set("operate")
    roots = [str(x) for x in existing.get("allowed_roots",[]) if str(x).strip()] or [str(Path.home().resolve())]
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

    brand = tk.Frame(sidebar,bg=C["sidebar"]); brand.pack(fill="x",padx=20,pady=(22,18))
    tk.Label(brand,text="L",font=(FONT,13,"bold"),fg=C["white"],bg=C["blue"],width=2,height=1).pack(side="left")
    tk.Label(brand,text="Lucas",font=(FONT,15,"bold"),fg=C["text"],bg=C["sidebar"]).pack(side="left",padx=(10,0))
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
        display.trace_add("write",lambda *_: var.set({v:k for k,v in DT.items()}.get(display.get(),"ask"))); return c

    # 常规
    wrap,body=scroll_page(); pages["常规"]=wrap
    section(body,"电脑"); c=card(body)
    row(c,"电脑名称","Windows 设备名称，只读。网页中的显示名称可单独修改。",lambda p: tk.Label(p,textvariable=node_name,font=(FONT,10),fg=C["muted"],bg=C["card"])); divider(c)
    row(c,"Node ID","设备唯一标识。",lambda p: tk.Label(p,textvariable=node_id,font=(FONT,9),fg=C["muted"],bg=C["card"]))
    section(body,"连接"); c=card(body)
    row(c,"Gateway","安全 WebSocket 地址。",lambda p: tk.Entry(p,textvariable=gateway,font=(FONT,10),relief="flat",bg=C["control"],fg=C["text"],bd=0,width=38)); divider(c)
    connection_status=tk.StringVar(value="检测中…")
    connection_status_label=None
    def build_connection_status(p):
        nonlocal connection_status_label
        connection_status_label=tk.Label(p,textvariable=connection_status,font=(FONT,9,"bold"),fg=C["muted"],bg=C["card"])
        return connection_status_label
    row(c,"连接状态","实时显示 Lucas 与 Gateway 的配对和连接状态。",build_connection_status); divider(c)

    def refresh_connection_status():
        paired=_has_saved_token()
        status_data={}
        try:
            loaded=json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded,dict): status_data=loaded
        except (OSError,json.JSONDecodeError): pass
        value=str(status_data.get("status") or "").strip()
        detail=str(status_data.get("detail") or "").strip().lower()
        if not paired:
            if "pairing" in detail or "token required" in detail:
                text,color="配对失败",C["red"]
            elif value in {"Connecting","Reconnecting"}:
                text,color="正在配对 / 连接…",C["orange"]
            else:
                text,color="未配对",C["orange"]
        elif value == "Online":
            text,color="已连接",C["green"]
        elif value == "Connecting":
            text,color="正在连接…",C["orange"]
        elif value == "Reconnecting":
            text,color="正在重新连接…",C["orange"]
        elif value in {"Disconnected","Offline"}:
            text,color="已配对 · 未连接",C["muted"]
        else:
            text,color="已配对 · 等待连接",C["muted"]
        connection_status.set(text); connection_status_label.configure(fg=color)
        try: root.after(1000,refresh_connection_status)
        except tk.TclError: pass

    pairing_control=None
    pairing_status=tk.StringVar(value=("已配对" if _has_saved_token() else "未配对"))
    pairing_entry=None
    pairing_status_label=None
    pairing_actions=None
    pairing_mode=tk.BooleanVar(value=not _has_saved_token())

    def build_pairing_control(p):
        nonlocal pairing_control,pairing_entry,pairing_status_label,pairing_actions
        pairing_control=tk.Frame(p,bg=C["card"])
        pairing_entry=tk.Entry(pairing_control,textvariable=pairing_code,font=(FONT,10),relief="flat",bg=C["control"],fg=C["text"],bd=0,width=20)
        pairing_status_label=tk.Label(pairing_control,textvariable=pairing_status,font=(FONT,9,"bold"),fg=C["green"],bg=C["card"])
        pairing_actions=tk.Frame(pairing_control,bg=C["card"])
        return pairing_control

    def refresh_pairing_control():
        for child in pairing_control.winfo_children():
            child.pack_forget()
        paired=_has_saved_token()
        if paired and not pairing_mode.get():
            pairing_status.set("已配对")
            pairing_status_label.configure(fg=C["green"]); pairing_status_label.pack(side="left",padx=(0,10))
            pairing_actions.pack(side="left")
            for child in pairing_actions.winfo_children(): child.destroy()
            button(pairing_actions,"重新配对",lambda: (pairing_mode.set(True),pairing_code.set(""),refresh_pairing_control(),root.after(50,pairing_entry.focus_set))).pack(side="left")
            button(pairing_actions,"取消配对",cancel_pairing,danger=True).pack(side="left",padx=(8,0))
        else:
            pairing_status.set("未配对" if not paired else "重新配对")
            pairing_status_label.configure(fg=(C["orange"] if not paired else C["blue"])); pairing_status_label.pack(side="left",padx=(0,10))
            pairing_entry.pack(side="left",ipady=6)
            if paired:
                button(pairing_control,"取消",lambda: (pairing_mode.set(False),pairing_code.set(""),refresh_pairing_control())).pack(side="left",padx=(8,0))

    def cancel_pairing():
        if not messagebox.askyesno("Lucas","取消这台电脑的配对？取消后 Lucas 会停止连接，需要新的 Pairing Code 才能重新连接。"): return
        try:
            STATE_FILE.unlink(missing_ok=True)
            pairing_code.set("")
            current=dict(existing)
            try:
                if CONFIG_FILE.exists():
                    loaded=json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                    if isinstance(loaded,dict): current.update(loaded)
            except (OSError,json.JSONDecodeError): pass
            current["pairing_code"]=None; current["connection_enabled"]=False
            _save_config(current)
            pairing_mode.set(True); refresh_pairing_control()
        except OSError as exc:
            messagebox.showerror("Lucas",f"无法取消配对：{exc}")

    row(c,"配对","首次安装、取消配对或重新配对都只在这里完成。Pairing Code 在 Lucas 网页生成。",build_pairing_control)
    refresh_pairing_control()

    section(body,"Lucas Node"); c=card(body)
    current_version=_app_version(); version_status=tk.StringVar(value=f"当前版本 {current_version} · 正在检查更新…"); update_button=None
    def run_update():
        if not messagebox.askyesno("Lucas","更新 Lucas Node？现有配对、Allowed Folders 和安全设置会保留。"): return
        try:
            script_path=Path(tempfile.gettempdir())/"Lucas-Node-update.ps1"
            urllib.request.urlretrieve(INSTALLER_URL,script_path)
            subprocess.Popen(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(script_path)],creationflags=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0))
            root.destroy()
        except Exception as exc:
            messagebox.showerror("Lucas",f"无法启动更新：{exc}")
    def build_update_control(p):
        nonlocal update_button
        update_button=button(p,"更新 Node",run_update,primary=True); update_button.configure(state="disabled"); return update_button
    row(c,"Lucas Node","检测到新版本时可直接升级；更新会保留本机现有配置。",build_update_control); divider(c)
    row(c,"版本状态","",lambda p: tk.Label(p,textvariable=version_status,font=(FONT,9,"bold"),fg=C["muted"],bg=C["card"]))
    def check_update_worker():
        latest=_fetch_latest_version()
        def apply_result():
            if not latest:
                version_status.set(f"当前版本 {current_version} · 无法检查更新"); return
            if current_version != "dev" and _version_key(latest)>_version_key(current_version):
                version_status.set(f"当前版本 {current_version} · 新版本 {latest} 可用"); update_button.configure(state="normal")
            else:
                version_status.set(f"当前版本 {current_version} · 已是最新版本")
        try: root.after(0,apply_result)
        except tk.TclError: pass
    threading.Thread(target=check_update_worker,daemon=True).start()

    # 安全
    wrap,body=scroll_page(); pages["安全"]=wrap
    section(body,"权限"); c=card(body)
    preset_syncing={"value":False}
    preset_display=tk.StringVar(value=detect_security_preset(permission.get(),{k:v.get() for k,v in approval_vars.items()},network_external.get(),network_lan.get(),block_silent_network.get()))
    preset_desc=tk.StringVar(value=PRESET_DESCRIPTIONS[preset_display.get()])
    def sync_preset_from_fields(*_):
        if preset_syncing["value"]: return
        name=detect_security_preset(permission.get(),{k:v.get() for k,v in approval_vars.items()},network_external.get(),network_lan.get(),block_silent_network.get())
        preset_syncing["value"]=True; preset_display.set(name); preset_desc.set(PRESET_DESCRIPTIONS[name]); preset_syncing["value"]=False
    def apply_preset(*_):
        if preset_syncing["value"]: return
        name=preset_display.get(); preset_desc.set(PRESET_DESCRIPTIONS.get(name,PRESET_DESCRIPTIONS["自定义"]))
        preset=PRESETS.get(name)
        if not preset: return
        preset_syncing["value"]=True
        permission.set(str(preset["permission_level"]))
        for k,v in preset["approval_policy"].items(): approval_vars[k].set(str(v))
        network_external.set(str(preset["network_external"])); network_lan.set(str(preset["network_lan"])); block_silent_network.set(bool(preset["block_silent_network"]))
        preset_syncing["value"]=False
    preset_display.trace_add("write",apply_preset)
    for var in [permission,network_external,network_lan,block_silent_network,*approval_vars.values()]: var.trace_add("write",sync_preset_from_fields)
    def preset_control(p):
        f=tk.Frame(p,bg=C["card"]); combo(f,preset_display,["请求批准（Recommended）","帮我批准","完全访问权限","自定义"],24).pack(anchor="e")
        tk.Label(f,textvariable=preset_desc,font=(FONT,8),fg=C["muted"],bg=C["card"],wraplength=290,justify="right").pack(anchor="e",pady=(4,0)); return f
    row(c,"快捷设置","选择预设后会立即同步下方审批策略与网络策略；手动修改任一项后自动变为“自定义”。",preset_control); divider(c)
    row(c,"权限来源","所有安全权限仅可在本机修改；网页只能查看。",lambda p: tk.Label(p,text="仅本机",font=(FONT,9,"bold"),fg=C["blue"],bg=C["card"]))
    section(body,"审批策略"); c=card(body)
    prs=[
        ("system_info","系统信息读取","读取进程、窗口、系统状态及项目只读信息。"),
        ("shell","普通 PowerShell / 命令行","运行不属于高风险分类的普通命令。"),
        ("file_write","文件写入与修改","创建、编辑、移动或复制文件。"),
        ("file_delete","文件删除","删除已授权目录中的文件或文件夹。"),
        ("process_control","进程启动 / 停止","启动程序、终止 Lucas 管理的进程或控制进程生命周期。"),
        ("service_control","Windows 服务启动 / 停止","启动、停止、重启或修改 Windows 服务。"),
        ("registry_system","注册表与系统配置","修改注册表、系统配置、电源、账户及受保护系统设置。"),
        ("software_install","安装 / 卸载软件","安装包管理器、MSI、winget、Chocolatey 或卸载软件。"),
        ("desktop_control","电脑操控","鼠标、键盘、窗口激活、输入、点击、滚动和 UI 自动化。"),
        ("screenshots","屏幕截图","读取当前屏幕内容用于 Computer Use。"),
        ("clipboard","剪贴板","读取或写入 Windows 剪贴板。"),
        ("browser_control","浏览器操控","打开页面、点击、输入、选择和浏览器自动化。"),
        ("browser_transfer","浏览器上传 / 下载","上传本地文件或下载文件到允许目录。"),
        ("git_write","Git 本地修改","add、commit、切换/创建分支等本地仓库写操作。"),
        ("git_push","Git Push / 远程写入","向远端仓库推送代码或其他远程写操作。"),
        ("high_risk","其他高风险系统修改","磁盘、账户、安全软件、关机重启等高风险操作。"),
    ]
    for i,(k,h,d) in enumerate(prs):
        row(c,h,d,lambda p,k=k: decision_control(p,approval_vars[k]))
        if i<len(prs)-1: divider(c)
    divider(c); row(c,"记住本次会话已批准操作","只记住完全相同操作；Lucas 重启后自动清除。",lambda p: switch(p,remember_approvals))

    # 文件访问
    wrap,body=scroll_page(); pages["文件访问"]=wrap
    section(body,"沙箱与文件访问"); c=card(body)
    tk.Label(c,text="仅允许访问以下文件夹",font=(FONT,10,"bold"),fg=C["text"],bg=C["card"]).pack(anchor="w",padx=18,pady=(16,4))
    tk.Label(c,text="文件读写、上传、下载与项目工作区都受此列表限制。",font=(FONT,9),fg=C["muted"],bg=C["card"]).pack(anchor="w",padx=18,pady=(0,10))
    lw=tk.Frame(c,bg=C["card"]); lw.pack(fill="both",padx=18,pady=(0,16))
    roots_list=tk.Listbox(lw,height=9,font=(FONT,10),bg=C["control"],fg=C["text"],relief="flat",bd=0,highlightthickness=1,highlightbackground=C["line"],selectbackground="#DCEEFF",selectforeground=C["text"])
    roots_list.pack(side="left",fill="both",expand=True)
    for item in roots: roots_list.insert("end",item)
    acts=tk.Frame(lw,bg=C["card"]); acts.pack(side="left",fill="y",padx=(10,0))
    def add_root():
        p=filedialog.askdirectory(title="选择 Lucas 可以访问的文件夹")
        if p and p not in roots_list.get(0,"end"): roots_list.insert("end",p)
    def remove_root():
        sel=roots_list.curselection()
        if sel: roots_list.delete(sel[0])
    button(acts,"添加文件夹",add_root,primary=True).pack(fill="x",pady=(0,8)); button(acts,"移除",remove_root,danger=True).pack(fill="x")
    c=card(body); row(c,"硬边界","不允许通过 shell、浏览器上传/下载、进程启动或路径参数绕过 Allowed Folders。",lambda p: tk.Label(p,text="已启用",font=(FONT,9,"bold"),fg=C["green"],bg=C["card"]))

    # 网络
    wrap,body=scroll_page(); pages["网络"]=wrap
    section(body,"网络访问"); c=card(body)
    row(c,"外部网络访问","访问互联网、远程 API、Git 远端等。",lambda p: decision_control(p,network_external)); divider(c)
    row(c,"本地局域网访问","localhost、私有 IP 与 .local 地址。",lambda p: decision_control(p,network_lan)); divider(c)
    row(c,"允许的域名","可选，逗号分隔；为空表示不额外限制域名。支持 *.example.com。",lambda p: tk.Entry(p,textvariable=allowed_domains,font=(FONT,10),relief="flat",bg=C["control"],fg=C["text"],bd=0,width=40)); divider(c)
    row(c,"阻止后台静默联网","无法识别目标地址的网络命令必须在本机确认。",lambda p: switch(p,block_silent_network))

    # 规则
    wrap,body=scroll_page(); pages["规则"]=wrap
    section(body,"本地 Rules"); c=card(body)
    tk.Label(c,text="本地安全规则",font=(FONT,10,"bold"),fg=C["text"],bg=C["card"]).pack(anchor="w",padx=18,pady=(16,4))
    tk.Label(c,text="需要确认的操作会把规则摘要一起显示在本机审批窗口。",font=(FONT,9),fg=C["muted"],bg=C["card"]).pack(anchor="w",padx=18,pady=(0,10))
    rules_text=tk.Text(c,height=8,font=(FONT,10),bg=C["control"],fg=C["text"],relief="flat",bd=0,wrap="word",padx=10,pady=9)
    rules_text.insert("1.0",rules_initial); rules_text.pack(fill="x",padx=18,pady=(0,14)); divider(c)
    row(c,"执行前显示规则摘要","审批时显示本地规则。",lambda p: switch(p,show_rule_summary))

    # 系统访问
    wrap,body=scroll_page(); pages["系统访问"]=wrap
    section(body,"Windows 权限"); c=card(body)
    row(c,"当前 Windows 权限","Lucas 应用权限与 Windows 管理员权限是两层独立控制。",lambda p: tk.Label(p,text=("管理员" if is_admin else "标准用户"),font=(FONT,10,"bold"),fg=(C["green"] if is_admin else C["orange"]),bg=C["card"])); divider(c)
    row(c,"Elevated / Admin",("当前进程已提升，可以执行 Windows 允许的管理员操作。" if is_admin else "服务、受保护注册表、驱动及部分硬件控制可能需要 Windows 管理员权限。"),lambda p: tk.Label(p,text=("已启用" if is_admin else "未启用"),font=(FONT,9,"bold"),fg=(C["green"] if is_admin else C["muted"]),bg=C["card"]))
    c=card(body); row(c,"重要","Full Access 不会自动提升 Windows 权限；Windows UAC 仍是最终系统边界。")

    desc={
        "常规":"连接身份与此电脑的 Lucas 基础配置。",
        "安全":"控制 AI 在这台电脑上可以执行的操作。安全设置只能在本机修改。",
        "文件访问":"使用 Allowed Folders 建立文件与工作区的硬边界。",
        "网络":"控制互联网、局域网、域名与后台网络请求。",
        "规则":"管理本机审批时展示的安全规则。",
        "系统访问":"查看 Lucas 与 Windows 管理员权限的实际状态。",
    }
    def show_page(name):
        for p in pages.values(): p.pack_forget()
        pages[name].pack(fill="both",expand=True); title.set(name); subtitle.set(desc[name])
        for k,b in nav_buttons.items(): b.configure(bg=("#E1E1E1" if k==name else C["sidebar"]),fg=C["text"])
    for name in ("常规","安全","文件访问","网络","规则","系统访问"):
        b=tk.Button(nav_frame,text=name,command=lambda n=name: show_page(n),font=(FONT,10),fg=C["text"],bg=C["sidebar"],activebackground=C["sidebar_hover"],activeforeground=C["text"],relief="flat",bd=0,anchor="w",padx=14,pady=9,cursor="hand2")
        b.pack(fill="x",pady=1); nav_buttons[name]=b
    sidebar_footer=tk.Frame(sidebar,bg=C["sidebar"]); sidebar_footer.pack(side="bottom",fill="x",padx=22,pady=20)
    tk.Label(sidebar_footer,text=f"Lucas v{_app_version()}",font=(FONT,8,"bold"),fg=C["muted"],bg=C["sidebar"]).pack(anchor="w")
    tk.Label(sidebar_footer,text="安全策略仅在此电脑上生效",font=(FONT,8),fg=C["subtle"],bg=C["sidebar"]).pack(anchor="w",pady=(3,0))

    footer=tk.Frame(main,bg=C["window"],highlightthickness=1,highlightbackground=C["line"]); footer.pack(fill="x",side="bottom")
    fi=tk.Frame(footer,bg=C["window"]); fi.pack(fill="x",padx=54,pady=12)
    tk.Label(fi,text="安全设置仅在此电脑上生效",font=(FONT,9),fg=C["muted"],bg=C["window"]).pack(side="left")

    result=None
    def reset_defaults():
        if not messagebox.askyesno("Lucas","恢复推荐的安全设置？Allowed Folders 不会被删除。"): return
        permission.set("operate"); mode_display.set("标准（Recommended）")
        defaults={"system_info":"allow","shell":"allow","file_write":"ask","file_delete":"ask","process_control":"ask","service_control":"ask","registry_system":"always_ask","software_install":"always_ask","desktop_control":"ask","screenshots":"allow","clipboard":"ask","browser_control":"ask","browser_transfer":"always_ask","git_write":"ask","git_push":"always_ask","high_risk":"always_ask"}
        for k,v in defaults.items(): approval_vars[k].set(v)
        remember_approvals.set(True); network_external.set("ask"); network_lan.set("allow"); allowed_domains.set(""); block_silent_network.set(True); show_rule_summary.set(True)
        rules_text.delete("1.0","end"); rules_text.insert("1.0","所有安全策略以本机设置为准；网页端只能查看，不能修改本机权限与允许目录。")

    def save():
        nonlocal result
        gv=gateway.get().strip()
        rv=[str(Path(v).expanduser().resolve()) for v in roots_list.get(0,"end") if str(v).strip()]
        if not gv.startswith(("ws://","wss://")): messagebox.showerror("Lucas","Gateway 必须以 ws:// 或 wss:// 开头。"); return
        if not node_name.get().strip() or not node_id.get().strip(): messagebox.showerror("Lucas","电脑名称和 Node ID 不能为空。"); return
        if not rv or any(not Path(v).is_dir() for v in rv): messagebox.showerror("Lucas","Allowed Folders 中的每个目录都必须真实存在。"); return
        domains=[v.strip().lower() for v in allowed_domains.get().replace(";",",").split(",") if v.strip()]
        code=pairing_code.get().strip()
        # Entering a pairing code explicitly starts a fresh pairing session. Keep
        # the old token until Save is pressed, then remove it so the next node
        # connection must exchange this code for a new token.
        if code:
            try:
                STATE_FILE.unlink(missing_ok=True)
            except OSError as exc:
                messagebox.showerror("Lucas",f"无法重置旧的配对状态：{exc}")
                return
        updated=dict(existing)
        updated.update({
            "gateway_ws_url":gv.rstrip("/"),"node_name":str(os.environ.get("COMPUTERNAME") or socket.gethostname()),"node_id":node_id.get().strip(),
            "pairing_code":code or None,"permission_level":permission.get(),"allowed_roots":rv,
            "security":{
                "approval_policy":{k:v.get() for k,v in approval_vars.items()},
                "remember_approvals":remember_approvals.get(),"network_external":network_external.get(),"network_lan":network_lan.get(),
                "allowed_domains":domains,"block_silent_network":block_silent_network.get(),
                "rules_text":rules_text.get("1.0","end").strip(),"show_rule_summary":show_rule_summary.get(),
            },
        })
        updated.setdefault("launch_at_startup",True)
        # Saving a pairing code also connects immediately. An unpaired install
        # without a code remains disconnected instead of retrying anonymously.
        if code:
            updated["connection_enabled"] = True
        elif not _has_saved_token():
            updated["connection_enabled"] = False
        else:
            updated.setdefault("connection_enabled",True)
        _save_config(updated); result=updated; root.destroy()

    button(fi,"保存更改",save,primary=True).pack(side="right")
    button(fi,"恢复默认",reset_defaults).pack(side="right",padx=(0,10))
    button(fi,"取消",root.destroy).pack(side="right",padx=(0,10))
    show_page("常规" if not _has_saved_token() else "安全")
    if not _has_saved_token():
        root.after(200, pairing_entry.focus_set)
    refresh_connection_status()
    root.mainloop()
    return result
