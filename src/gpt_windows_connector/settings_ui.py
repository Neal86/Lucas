from __future__ import annotations

import ctypes
import json
import os
import socket
import uuid
from pathlib import Path
from typing import Any

APP_NAME = "Lucas"
DEFAULT_GATEWAY = "wss://lucasmcp.com/ws/node"
CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "node-config.json"

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
    node_name = tk.StringVar(value=str(existing.get("node_name") or os.environ.get("COMPUTERNAME") or socket.gethostname()))
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

    def scroll_page():
        wrapper=tk.Frame(page_host,bg=C["window"]); canvas=tk.Canvas(wrapper,bg=C["window"],highlightthickness=0,bd=0)
        sb=ttk.Scrollbar(wrapper,orient="vertical",command=canvas.yview); body=tk.Frame(canvas,bg=C["window"])
        win=canvas.create_window((0,0),window=body,anchor="nw")
        body.bind("<Configure>",lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda e: canvas.itemconfigure(win,width=e.width))
        canvas.configure(yscrollcommand=sb.set); canvas.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
        canvas.bind_all("<MouseWheel>",lambda e: canvas.yview_scroll(int(-1*(e.delta/120)),"units") if wrapper.winfo_ismapped() else None)
        return wrapper,body

    def section(parent,text):
        tk.Label(parent,text=text,font=(FONT,12,"bold"),fg=C["text"],bg=C["window"]).pack(anchor="w",pady=(18,10))
    def card(parent):
        f=tk.Frame(parent,bg=C["card"],highlightthickness=1,highlightbackground=C["line"]); f.pack(fill="x",pady=(0,16)); return f
    def divider(parent):
        tk.Frame(parent,bg=C["line"],height=1).pack(fill="x",padx=18)
    def row(parent,heading,desc="",control=None):
        r=tk.Frame(parent,bg=C["card"]); r.pack(fill="x",padx=18,pady=13)
        copy=tk.Frame(r,bg=C["card"]); copy.pack(side="left",fill="x",expand=True)
        tk.Label(copy,text=heading,font=(FONT,10,"bold"),fg=C["text"],bg=C["card"]).pack(anchor="w")
        if desc: tk.Label(copy,text=desc,font=(FONT,9),fg=C["muted"],bg=C["card"],wraplength=600,justify="left").pack(anchor="w",pady=(3,0))
        if control is not None: control.pack(in_=r,side="right",padx=(18,0))
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
    name_entry=tk.Entry(c,textvariable=node_name,font=(FONT,10),relief="flat",bg=C["control"],fg=C["text"],bd=0,width=32)
    row(c,"电脑名称","用于在 Lucas 中识别这台电脑。",name_entry); divider(c)
    row(c,"Node ID","设备唯一标识。",tk.Label(c,textvariable=node_id,font=(FONT,9),fg=C["muted"],bg=C["card"]))
    section(body,"连接"); c=card(body)
    row(c,"Gateway","安全 WebSocket 地址。",tk.Entry(c,textvariable=gateway,font=(FONT,10),relief="flat",bg=C["control"],fg=C["text"],bd=0,width=38)); divider(c)
    row(c,"配对码","仅重新配对时需要。",tk.Entry(c,textvariable=pairing_code,font=(FONT,10),relief="flat",bg=C["control"],fg=C["text"],bd=0,width=20))

    # 安全
    wrap,body=scroll_page(); pages["安全"]=wrap
    section(body,"权限"); c=card(body)
    mode_display=tk.StringVar(value={"read":"只读（Safe）","operate":"标准（Recommended）","admin":"完整访问（Advanced）"}.get(permission.get(),"标准（Recommended）"))
    mc=combo(c,mode_display,["只读（Safe）","标准（Recommended）","完整访问（Advanced）"],23)
    mode_display.trace_add("write",lambda *_: permission.set({"只读（Safe）":"read","标准（Recommended）":"operate","完整访问（Advanced）":"admin"}.get(mode_display.get(),"operate")))
    row(c,"默认权限","基础能力上限。完整访问不会绕过 Windows UAC。",mc); divider(c)
    row(c,"权限来源","所有安全权限仅可在本机修改；网页只能查看。",tk.Label(c,text="仅本机",font=(FONT,9,"bold"),fg=C["blue"],bg=C["card"]))
    section(body,"审批策略"); c=card(body)
    prs=[
        ("system_info","系统信息读取","读取进程、窗口、系统状态及项目只读信息。"),
        ("shell","普通 PowerShell / 命令行","运行不属于高风险分类的普通命令。"),
        ("file_write","文件写入与修改","创建、编辑、移动或复制文件。"),
        ("file_delete","文件删除","删除已授权目录中的文件或文件夹。"),
        ("service_control","服务启动 / 停止","启动、停止、重启或修改 Windows 服务。"),
        ("high_risk","高风险系统修改","注册表、系统配置、账号、磁盘、发布等高风险操作。"),
    ]
    for i,(k,h,d) in enumerate(prs):
        row(c,h,d,decision_control(c,approval_vars[k]))
        if i<len(prs)-1: divider(c)
    divider(c); row(c,"记住本次会话已批准操作","只记住完全相同操作；Lucas 重启后自动清除。",switch(c,remember_approvals))

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
    c=card(body); row(c,"硬边界","不允许通过 shell、浏览器上传/下载、进程启动或路径参数绕过 Allowed Folders。",tk.Label(c,text="已启用",font=(FONT,9,"bold"),fg=C["green"],bg=C["card"]))

    # 网络
    wrap,body=scroll_page(); pages["网络"]=wrap
    section(body,"网络访问"); c=card(body)
    row(c,"外部网络访问","访问互联网、远程 API、Git 远端等。",decision_control(c,network_external)); divider(c)
    row(c,"本地局域网访问","localhost、私有 IP 与 .local 地址。",decision_control(c,network_lan)); divider(c)
    row(c,"允许的域名","可选，逗号分隔；为空表示不额外限制域名。支持 *.example.com。",tk.Entry(c,textvariable=allowed_domains,font=(FONT,10),relief="flat",bg=C["control"],fg=C["text"],bd=0,width=40)); divider(c)
    row(c,"阻止后台静默联网","无法识别目标地址的网络命令必须在本机确认。",switch(c,block_silent_network))

    # 规则
    wrap,body=scroll_page(); pages["规则"]=wrap
    section(body,"本地 Rules"); c=card(body)
    tk.Label(c,text="本地安全规则",font=(FONT,10,"bold"),fg=C["text"],bg=C["card"]).pack(anchor="w",padx=18,pady=(16,4))
    tk.Label(c,text="需要确认的操作会把规则摘要一起显示在本机审批窗口。",font=(FONT,9),fg=C["muted"],bg=C["card"]).pack(anchor="w",padx=18,pady=(0,10))
    rules_text=tk.Text(c,height=8,font=(FONT,10),bg=C["control"],fg=C["text"],relief="flat",bd=0,wrap="word",padx=10,pady=9)
    rules_text.insert("1.0",rules_initial); rules_text.pack(fill="x",padx=18,pady=(0,14)); divider(c)
    row(c,"执行前显示规则摘要","审批时显示本地规则。",switch(c,show_rule_summary))

    # 系统访问
    wrap,body=scroll_page(); pages["系统访问"]=wrap
    section(body,"Windows 权限"); c=card(body)
    row(c,"当前 Windows 权限","Lucas 应用权限与 Windows 管理员权限是两层独立控制。",tk.Label(c,text=("管理员" if is_admin else "标准用户"),font=(FONT,10,"bold"),fg=(C["green"] if is_admin else C["orange"]),bg=C["card"])); divider(c)
    row(c,"Elevated / Admin",("当前进程已提升，可以执行 Windows 允许的管理员操作。" if is_admin else "服务、受保护注册表、驱动及部分硬件控制可能需要 Windows 管理员权限。"),tk.Label(c,text=("已启用" if is_admin else "未启用"),font=(FONT,9,"bold"),fg=(C["green"] if is_admin else C["muted"]),bg=C["card"]))
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
    tk.Label(sidebar,text="安全策略仅在此电脑上生效",font=(FONT,8),fg=C["subtle"],bg=C["sidebar"]).pack(side="bottom",anchor="w",padx=22,pady=20)

    footer=tk.Frame(main,bg=C["window"],highlightthickness=1,highlightbackground=C["line"]); footer.pack(fill="x",side="bottom")
    fi=tk.Frame(footer,bg=C["window"]); fi.pack(fill="x",padx=54,pady=12)
    tk.Label(fi,text="安全设置仅在此电脑上生效",font=(FONT,9),fg=C["muted"],bg=C["window"]).pack(side="left")

    result=None
    def reset_defaults():
        if not messagebox.askyesno("Lucas","恢复推荐的安全设置？Allowed Folders 不会被删除。"): return
        permission.set("operate"); mode_display.set("标准（Recommended）")
        defaults={"system_info":"allow","shell":"allow","file_write":"ask","file_delete":"ask","service_control":"ask","high_risk":"always_ask"}
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
        updated=dict(existing)
        updated.update({
            "gateway_ws_url":gv.rstrip("/"),"node_name":node_name.get().strip(),"node_id":node_id.get().strip(),
            "pairing_code":pairing_code.get().strip() or None,"permission_level":permission.get(),"allowed_roots":rv,
            "security":{
                "approval_policy":{k:v.get() for k,v in approval_vars.items()},
                "remember_approvals":remember_approvals.get(),"network_external":network_external.get(),"network_lan":network_lan.get(),
                "allowed_domains":domains,"block_silent_network":block_silent_network.get(),
                "rules_text":rules_text.get("1.0","end").strip(),"show_rule_summary":show_rule_summary.get(),
            },
        })
        updated.setdefault("connection_enabled",True); updated.setdefault("launch_at_startup",True)
        _save_config(updated); result=updated; root.destroy()

    button(fi,"保存更改",save,primary=True).pack(side="right")
    button(fi,"恢复默认",reset_defaults).pack(side="right",padx=(0,10))
    button(fi,"取消",root.destroy).pack(side="right",padx=(0,10))
    show_page("安全")
    root.mainloop()
    return result
