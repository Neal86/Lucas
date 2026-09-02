from __future__ import annotations

from .i18n import tr

def prompt_access_request(actor: dict[str, object], node_roots: list[str]) -> dict[str, object]:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:
        return {"decision": "deny", "error": f"approval UI unavailable: {exc}"}

    result: dict[str, object] = {"decision": "deny"}
    root = tk.Tk()
    root.title(tr("Lucas 访问请求", "Lucas Access Request"))
    root.geometry("580x540")
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
    tk.Label(frame, text=tr("连接码已验证。请选择一个快捷权限模式；详细权限可以稍后在 Lucas 设置 → 用户与权限 中修改。", "The connection code is verified. Choose a quick access mode; detailed permissions can be changed later in Lucas Settings → Users & Permissions."), font=("Segoe UI", 9), fg="#555555", wraplength=520, justify="left").pack(anchor="w", pady=(10, 18))

    tk.Label(frame, text=tr("快捷权限", "Quick access mode"), font=("Segoe UI", 9, "bold")).pack(anchor="w")
    preset_display = tk.StringVar(value=tr("请求批准（Recommended）", "Ask for approval (Recommended)"))
    preset_values = [tr("请求批准（Recommended）", "Ask for approval (Recommended)"), tr("帮我批准", "Auto-approve safe actions"), tr("完全访问权限", "Full Access")]
    ttk.Combobox(frame, textvariable=preset_display, values=preset_values, state="readonly", width=34).pack(anchor="w", pady=(5, 14))

    tk.Label(frame, text=tr("允许访问的文件夹", "Allowed folders"), font=("Segoe UI", 9, "bold")).pack(anchor="w")
    folders = tk.Listbox(frame, selectmode="multiple", height=min(max(len(node_roots), 4), 9), width=72)
    folders.pack(fill="x", pady=(5, 8))
    for index, path in enumerate(node_roots):
        folders.insert("end", path)
        folders.selection_set(index)
    tk.Label(frame, text=tr("该账号只能访问这里选择的文件夹；Windows UAC 仍然是最终系统权限边界。", "This account can access only the selected folders; Windows UAC remains the final system privilege boundary."), font=("Segoe UI", 8), fg="#777777", wraplength=520, justify="left").pack(anchor="w")

    actions = tk.Frame(frame)
    actions.pack(side="bottom", fill="x", pady=(24, 0))

    def finish(decision: str) -> None:
        selected = [node_roots[i] for i in folders.curselection()]
        preset_map = {preset_values[0]: "request_approval", preset_values[1]: "auto_approve", preset_values[2]: "full_access"}
        result.update({"decision": decision, "preset": preset_map.get(preset_display.get(), "request_approval"), "allowed_roots": selected})
        root.destroy()

    tk.Button(actions, text=tr("拒绝", "Deny"), command=lambda: finish("deny"), padx=14, pady=7).pack(side="right")
    tk.Button(actions, text=tr("允许一次", "Allow once"), command=lambda: finish("once"), padx=14, pady=7).pack(side="right", padx=(0, 8))
    tk.Button(actions, text=tr("长期允许", "Always allow"), command=lambda: finish("always"), padx=14, pady=7).pack(side="right", padx=(0, 8))
    root.protocol("WM_DELETE_WINDOW", lambda: finish("deny"))
    root.mainloop()
    return result
