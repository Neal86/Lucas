from __future__ import annotations

import os
import socket
import subprocess
from typing import Any

from .browser_bridge_extension_files import prepare_extension
from .browser_profile_registry import registry


def build_browser_page(*, tk, parent, colors: dict[str, str], font: str, translate):
    T = translate
    C = colors
    frame = tk.Frame(parent, bg=C["window"])
    canvas = tk.Canvas(frame, bg=C["window"], highlightthickness=0, bd=0)
    scrollbar = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
    body = tk.Frame(canvas, bg=C["window"])
    win = canvas.create_window((0, 0), window=body, anchor="nw")
    body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    frame._lucas_canvas = canvas

    def section(text):
        tk.Label(body, text=text, font=(font, 12, "bold"), fg=C["text"], bg=C["window"]).pack(anchor="w", pady=(18, 10))

    def card():
        item = tk.Frame(body, bg=C["card"], highlightthickness=1, highlightbackground=C["line"])
        item.pack(fill="x", pady=(0, 16))
        return item

    def button(parent_, text, command, primary=False):
        return tk.Button(
            parent_, text=text, command=command, font=(font, 9, "bold"),
            fg=("#FFFFFF" if primary else C["text"]),
            bg=(C["blue"] if primary else C["control"]),
            activebackground=(C["blue_dark"] if primary else C["control_hover"]),
            activeforeground=("#FFFFFF" if primary else C["text"]),
            relief="flat", bd=0, padx=12, pady=7, cursor="hand2",
        )

    section(T("Browser Bridge", "Browser Bridge"))
    bridge_card = card()
    extension_status = tk.StringVar(value=T("准备中…", "Preparing…"))
    bridge_status = tk.StringVar(value=T("检测中…", "Checking…"))
    extension_path = tk.StringVar(value="")

    top = tk.Frame(bridge_card, bg=C["card"])
    top.pack(fill="x", padx=18, pady=(14, 8))
    tk.Label(top, text=T("Lucas Browser Bridge 扩展", "Lucas Browser Bridge extension"), font=(font, 10, "bold"), fg=C["text"], bg=C["card"]).pack(anchor="w")
    tk.Label(top, textvariable=extension_status, font=(font, 9), fg=C["muted"], bg=C["card"]).pack(anchor="w", pady=(5, 0))
    tk.Label(top, textvariable=extension_path, font=(font, 8), fg=C["subtle"], bg=C["card"], wraplength=720, justify="left").pack(anchor="w", pady=(3, 0))
    tk.Label(top, textvariable=bridge_status, font=(font, 9, "bold"), fg=C["blue"], bg=C["card"]).pack(anchor="w", pady=(8, 0))
    actions = tk.Frame(bridge_card, bg=C["card"])
    actions.pack(fill="x", padx=18, pady=(0, 14))

    def refresh_bridge():
        try:
            info = prepare_extension()
            extension_path.set(str(info["path"]))
            extension_status.set(T("扩展文件已就绪", "Extension files are ready"))
        except Exception as exc:
            extension_status.set(T("扩展准备失败：", "Extension preparation failed: ") + str(exc))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.25)
        try:
            ok = sock.connect_ex(("127.0.0.1", 8766)) == 0
        finally:
            sock.close()
        bridge_status.set(T("本地 Bridge 服务已运行", "Local Bridge service is running") if ok else T("本地 Bridge 服务未运行；启动/重启 Lucas Node 后会自动运行", "Local Bridge service is not running; restart Lucas Node to start it"))

    def open_extension_folder():
        try:
            info = prepare_extension()
            if os.name == "nt":
                os.startfile(info["path"])
            else:
                subprocess.Popen(["xdg-open", info["path"]])
        except Exception:
            pass

    button(actions, T("刷新", "Refresh"), refresh_bridge).pack(side="left")
    button(actions, T("打开扩展文件夹", "Open extension folder"), open_extension_folder, primary=True).pack(side="left", padx=(8, 0))

    section(T("Browser Profiles", "Browser Profiles"))
    profile_card = card()
    profile_list = tk.Listbox(profile_card, height=10, font=(font, 9), bg=C["control"], fg=C["text"], relief="flat", bd=0)
    profile_list.pack(fill="x", padx=18, pady=(14, 8))
    profile_records: list[dict[str, Any]] = []

    editor = tk.Frame(profile_card, bg=C["card"])
    editor.pack(fill="x", padx=18, pady=(0, 10))
    fields = {}
    labels = [
        ("browser_type", T("浏览器类型", "Browser type")),
        ("profile_name", T("名称", "Name")),
        ("profile_id", "Profile ID"),
        ("aliases", T("别名（逗号分隔）", "Aliases (comma separated)")),
        ("groups", T("分组（逗号分隔）", "Groups (comma separated)")),
        ("tags", T("标签（逗号分隔）", "Tags (comma separated)")),
        ("cdp_endpoint", "CDP endpoint"),
        ("launcher_executable", T("本地启动程序", "Local launcher executable")),
        ("launcher_args", T("启动参数（用 | 分隔）", "Launcher args (separate with |)")),
    ]
    for index, (key, label) in enumerate(labels):
        row = index // 2
        col = (index % 2) * 2
        tk.Label(editor, text=label, font=(font, 8, "bold"), fg=C["muted"], bg=C["card"]).grid(row=row, column=col, sticky="w", padx=(0, 6), pady=4)
        var = tk.StringVar()
        fields[key] = var
        tk.Entry(editor, textvariable=var, font=(font, 9), bg=C["control"], fg=C["text"], relief="flat", bd=0, width=28).grid(row=row, column=col + 1, sticky="ew", padx=(0, 16), pady=4, ipady=5)
    editor.grid_columnconfigure(1, weight=1)
    editor.grid_columnconfigure(3, weight=1)

    selected_profile_key = {"value": ""}

    def refresh_profiles():
        profile_records[:] = registry.list_profiles(include_disabled=True)
        profile_list.delete(0, "end")
        for item in profile_records:
            aliases = ",".join(item.get("aliases") or [])
            suffix = (" · " + aliases) if aliases else ""
            profile_list.insert("end", f"{item.get('browser_type') or 'browser'} · {item.get('profile_name') or item.get('profile_id') or item.get('profile_key')}{suffix}")

    def select_profile(_event=None):
        indexes = profile_list.curselection()
        if not indexes:
            return
        item = profile_records[indexes[0]]
        selected_profile_key["value"] = str(item.get("profile_key") or "")
        for key, var in fields.items():
            if key == "launcher_executable":
                value = (item.get("launcher") or {}).get("executable")
            elif key == "launcher_args":
                value = " | ".join(str(v) for v in (item.get("launcher") or {}).get("args") or [])
            else:
                value = item.get(key)
            if isinstance(value, list):
                value = ", ".join(value)
            var.set(str(value or ""))

    profile_list.bind("<<ListboxSelect>>", select_profile)

    def save_profile():
        launcher_executable = fields["launcher_executable"].get().strip()
        launcher_args = [v.strip() for v in fields["launcher_args"].get().split("|") if v.strip()]
        payload = {
            "profile_key": selected_profile_key["value"],
            "browser_type": fields["browser_type"].get().strip().lower() or "ixbrowser",
            "profile_name": fields["profile_name"].get().strip(),
            "profile_id": fields["profile_id"].get().strip(),
            "aliases": [v.strip() for v in fields["aliases"].get().split(",") if v.strip()],
            "groups": [v.strip() for v in fields["groups"].get().split(",") if v.strip()],
            "tags": [v.strip() for v in fields["tags"].get().split(",") if v.strip()],
            "cdp_endpoint": fields["cdp_endpoint"].get().strip(),
            "launcher": ({
                "kind": "command",
                "executable": launcher_executable,
                "args": launcher_args,
            } if launcher_executable else {}),
            "enabled": True,
        }
        result = registry.upsert_profile(payload)
        selected_profile_key["value"] = str(result["profile_key"])
        refresh_profiles()

    def new_profile():
        selected_profile_key["value"] = ""
        for var in fields.values():
            var.set("")
        fields["browser_type"].set("ixbrowser")

    def delete_profile():
        key = selected_profile_key["value"]
        if key:
            registry.remove_profile(key)
            new_profile()
            refresh_profiles()

    profile_actions = tk.Frame(profile_card, bg=C["card"])
    profile_actions.pack(fill="x", padx=18, pady=(0, 14))
    button(profile_actions, T("新增", "New"), new_profile).pack(side="left")
    button(profile_actions, T("保存", "Save"), save_profile, primary=True).pack(side="left", padx=(8, 0))
    button(profile_actions, T("删除", "Delete"), delete_profile).pack(side="left", padx=(8, 0))
    button(profile_actions, T("刷新", "Refresh"), refresh_profiles).pack(side="right")

    section(T("Agent → Browser Profile 权限", "Agent → Browser Profile permissions"))
    policy_card = card()
    policy_list = tk.Listbox(policy_card, height=7, font=(font, 9), bg=C["control"], fg=C["text"], relief="flat", bd=0)
    policy_list.pack(fill="x", padx=18, pady=(14, 8))
    policy_records: list[dict[str, Any]] = []
    policy_fields = {}
    policy_editor = tk.Frame(policy_card, bg=C["card"])
    policy_editor.pack(fill="x", padx=18, pady=(0, 10))
    policy_labels = [
        ("agent_key", T("Agent / Client", "Agent / Client")),
        ("default_profile", T("默认 Profile/别名", "Default profile/alias")),
        ("allow_aliases", T("允许别名", "Allowed aliases")),
        ("allow_groups", T("允许分组", "Allowed groups")),
        ("allow_tags", T("允许标签", "Allowed tags")),
        ("deny_groups", T("禁止分组", "Denied groups")),
    ]
    for index, (key, label) in enumerate(policy_labels):
        row = index // 2
        col = (index % 2) * 2
        tk.Label(policy_editor, text=label, font=(font, 8, "bold"), fg=C["muted"], bg=C["card"]).grid(row=row, column=col, sticky="w", padx=(0, 6), pady=4)
        var = tk.StringVar()
        policy_fields[key] = var
        tk.Entry(policy_editor, textvariable=var, font=(font, 9), bg=C["control"], fg=C["text"], relief="flat", bd=0, width=28).grid(row=row, column=col + 1, sticky="ew", padx=(0, 16), pady=4, ipady=5)
    policy_editor.grid_columnconfigure(1, weight=1)
    policy_editor.grid_columnconfigure(3, weight=1)
    selected_agent = {"value": ""}

    def refresh_policies():
        policy_records[:] = registry.list_agent_policies()
        policy_list.delete(0, "end")
        for item in policy_records:
            policy_list.insert("end", f"{item.get('agent_key')} → {item.get('default_profile') or 'allowed set'}")

    def select_policy(_event=None):
        indexes = policy_list.curselection()
        if not indexes:
            return
        item = policy_records[indexes[0]]
        selected_agent["value"] = str(item.get("agent_key") or "")
        for key, var in policy_fields.items():
            value = item.get(key)
            if isinstance(value, list):
                value = ", ".join(value)
            var.set(str(value or ""))

    policy_list.bind("<<ListboxSelect>>", select_policy)

    def save_policy():
        agent = policy_fields["agent_key"].get().strip()
        if not agent:
            return
        result = registry.set_agent_policy(agent, {
            "default_profile": policy_fields["default_profile"].get().strip(),
            "allow_aliases": [v.strip() for v in policy_fields["allow_aliases"].get().split(",") if v.strip()],
            "allow_groups": [v.strip() for v in policy_fields["allow_groups"].get().split(",") if v.strip()],
            "allow_tags": [v.strip() for v in policy_fields["allow_tags"].get().split(",") if v.strip()],
            "deny_groups": [v.strip() for v in policy_fields["deny_groups"].get().split(",") if v.strip()],
            "enabled": True,
        })
        selected_agent["value"] = str(result["agent_key"])
        refresh_policies()

    def new_policy():
        selected_agent["value"] = ""
        for var in policy_fields.values():
            var.set("")

    def delete_policy():
        agent = selected_agent["value"] or policy_fields["agent_key"].get().strip()
        if agent:
            registry.remove_agent_policy(agent)
            new_policy()
            refresh_policies()

    policy_actions = tk.Frame(policy_card, bg=C["card"])
    policy_actions.pack(fill="x", padx=18, pady=(0, 14))
    button(policy_actions, T("新增", "New"), new_policy).pack(side="left")
    button(policy_actions, T("保存", "Save"), save_policy, primary=True).pack(side="left", padx=(8, 0))
    button(policy_actions, T("删除", "Delete"), delete_policy).pack(side="left", padx=(8, 0))
    button(policy_actions, T("刷新", "Refresh"), refresh_policies).pack(side="right")

    tk.Label(
        body,
        text=T(
            "规则保存在本机。Agent 无法通过远程 MCP 修改自己的 Browser Profile 权限。",
            "Rules are stored locally. An agent cannot change its own Browser Profile permissions through remote MCP.",
        ),
        font=(font, 8), fg=C["muted"], bg=C["window"], wraplength=760, justify="left",
    ).pack(anchor="w", pady=(0, 20))

    refresh_bridge()
    refresh_profiles()
    refresh_policies()
    return frame
