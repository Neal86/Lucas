from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable


class InAppUpdater:
    """Transient in-app update surface for the Windows Settings application."""

    def __init__(
        self,
        *,
        root: Any,
        tk: Any,
        ttk: Any,
        page_host: Any,
        pages: dict[str, Any],
        nav_buttons: dict[str, Any],
        button_factory: Callable[..., Any],
        get_footer: Callable[[], Any],
        show_page: Callable[[str], None],
        title: Any,
        subtitle: Any,
        translate: Callable[[str, str], str],
        colors: dict[str, str],
        font: str,
        current_version: str,
        version_status: Any,
        fetch_latest_version: Callable[[], str | None],
        version_key: Callable[[str], tuple[int, ...]],
        installer_url: str,
        load_last_page: Callable[[], str],
        save_last_page: Callable[[str], None],
        before_update: Callable[[], None] | None = None,
    ) -> None:
        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.page_host = page_host
        self.pages = pages
        self.nav_buttons = nav_buttons
        self.button_factory = button_factory
        self.get_footer = get_footer
        self.show_page = show_page
        self.title = title
        self.subtitle = subtitle
        self.T = translate
        self.C = colors
        self.FONT = font
        self.current_version = current_version
        self.version_status = version_status
        self.fetch_latest_version = fetch_latest_version
        self.version_key = version_key
        self.installer_url = installer_url
        self.load_last_page = load_last_page
        self.save_last_page = save_last_page
        self.before_update = before_update
        self.update_button = None
        self.check_update_button = None
        self.state = {"frame": None, "active": False, "return_page": "常规", "success": False, "target": ""}
        self.widgets: dict[str, Any] = {}
        self.stage_labels = {
            "prepare": self.T("准备更新…", "Preparing update…"),
            "runtime": self.T("检查运行环境…", "Checking runtime…"),
            "install": self.T("下载并安装 Lucas…", "Downloading and installing Lucas…"),
            "verify": self.T("验证新版本…", "Verifying the new version…"),
            "startup": self.T("重新启动后台服务…", "Restarting background services…"),
            "complete": self.T("更新完成", "Update complete"),
        }

    def build_control(self, parent: Any) -> Any:
        control = self.tk.Frame(parent, bg=self.C["card"])
        self.tk.Label(
            control,
            textvariable=self.version_status,
            font=(self.FONT, 9, "bold"),
            fg=self.C["muted"],
            bg=self.C["card"],
        ).pack(side="left")
        self.check_update_button = self.button_factory(control, "检测更新", self.start_check)
        self.check_update_button.pack(side="left", padx=(12, 0))
        self.update_button = self.button_factory(control, "更新 Node", self.run_update, primary=True)
        self.update_button.pack(side="left", padx=(8, 0))
        self.update_button.configure(state="disabled")
        return control

    def start_check(self) -> None:
        threading.Thread(target=self._check_update_worker, daemon=True).start()

    def start_auto_check(self) -> None:
        threading.Thread(target=self._check_update_worker, daemon=True).start()

    def _append_log(self, line: str) -> None:
        widget = self.widgets.get("log")
        if widget is None or not widget.winfo_exists():
            return
        widget.configure(state="normal")
        widget.insert("end", line.rstrip() + "\n")
        widget.configure(state="disabled")
        widget.see("end")

    def _set_progress(self, percent: int, stage: str) -> None:
        progress = self.widgets.get("progress")
        phase = self.widgets.get("phase")
        if progress is not None:
            progress.set(max(0, min(100, int(percent))))
        if phase is not None:
            phase.set(self.stage_labels.get(stage, stage))

    def _set_nav_enabled(self, enabled: bool) -> None:
        for nav in self.nav_buttons.values():
            try:
                nav.configure(state=("normal" if enabled else "disabled"))
            except self.tk.TclError:
                pass

    def _show_update_page(self, target_version: str = "") -> None:
        if not self.state["active"]:
            self.state["return_page"] = self.load_last_page()
        self.state["active"] = True
        self.state["success"] = False
        self.state["target"] = target_version or self.state.get("target") or ""
        for page in self.pages.values():
            page.pack_forget()
        try:
            self.get_footer().pack_forget()
        except Exception:
            pass
        self._set_nav_enabled(False)
        self.title.set(self.T("正在更新 Lucas", "Updating Lucas"))
        self.subtitle.set(
            self.T(
                "更新过程中请保持 Lucas 打开。完成后点击返回即可回到原界面。",
                "Keep Lucas open during the update. When it finishes, use Return to go back.",
            )
        )
        frame = self.state.get("frame")
        if frame is None or not frame.winfo_exists():
            frame = self.tk.Frame(self.page_host, bg=self.C["window"])
            self.state["frame"] = frame
            card = self.tk.Frame(frame, bg=self.C["card"], highlightthickness=1, highlightbackground=self.C["line"])
            card.pack(fill="both", expand=True, pady=(8, 14))
            top = self.tk.Frame(card, bg=self.C["card"])
            top.pack(fill="x", padx=24, pady=(22, 10))
            version_var = self.tk.StringVar(value="")
            self.widgets["version"] = version_var
            self.tk.Label(top, textvariable=version_var, font=(self.FONT, 11, "bold"), fg=self.C["text"], bg=self.C["card"]).pack(anchor="w")
            phase = self.tk.StringVar(value=self.stage_labels["prepare"])
            self.widgets["phase"] = phase
            self.tk.Label(top, textvariable=phase, font=(self.FONT, 9), fg=self.C["muted"], bg=self.C["card"]).pack(anchor="w", pady=(5, 0))
            progress = self.tk.IntVar(value=0)
            self.widgets["progress"] = progress
            self.ttk.Progressbar(card, maximum=100, variable=progress, mode="determinate").pack(fill="x", padx=24, pady=(4, 14))
            log = self.tk.Text(
                card,
                height=20,
                font=("Consolas", 9),
                bg="#111111",
                fg="#E6E6E6",
                insertbackground="#FFFFFF",
                relief="flat",
                bd=0,
                wrap="word",
                padx=10,
                pady=10,
                state="disabled",
            )
            log.pack(fill="both", expand=True, padx=24, pady=(0, 14))
            self.widgets["log"] = log
            actions = self.tk.Frame(card, bg=self.C["card"])
            actions.pack(fill="x", padx=24, pady=(0, 20))
            self.widgets["return_button"] = self.button_factory(
                actions,
                self.T("返回", "Return"),
                lambda: self._leave_update_page(bool(self.state.get("success"))),
                primary=True,
            )
            self.widgets["retry_button"] = self.button_factory(actions, self.T("重试更新", "Retry update"), self.run_update)
        frame.pack(fill="both", expand=True)
        self.widgets["version"].set(
            f"Lucas {self.current_version}  →  {target_version}" if target_version else f"Lucas {self.current_version}"
        )
        log = self.widgets["log"]
        log.configure(state="normal")
        log.delete("1.0", "end")
        log.configure(state="disabled")
        for key in ("return_button", "retry_button"):
            self.widgets[key].pack_forget()
        self._set_progress(3, "prepare")

    def _leave_update_page(self, restart_after_update: bool = False) -> None:
        self.state["active"] = False
        frame = self.state.get("frame")
        if frame is not None and frame.winfo_exists():
            frame.pack_forget()
        self._set_nav_enabled(True)
        return_page = str(self.state.get("return_page") or "常规")
        if restart_after_update:
            self.save_last_page(return_page)
            env = os.environ.copy()
            env["LUCAS_SETTINGS_PAGE"] = return_page
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                subprocess.Popen(
                    [sys.executable, "-m", "gpt_windows_connector.node", "--configure"],
                    env=env,
                    creationflags=flags,
                )
            finally:
                self.root.destroy()
            return
        self.get_footer().pack(fill="x", side="bottom")
        self.show_page(return_page)

    def _finish_update(self, success: bool, target_version: str, message: str = "") -> None:
        self.state["success"] = bool(success)
        self.state["target"] = target_version or self.state.get("target") or ""
        if success:
            self._set_progress(100, "complete")
            self.widgets["version"].set(
                self.T(f"Lucas 已更新至 {target_version}", f"Lucas has been updated to {target_version}")
            )
            self.widgets["return_button"].pack(side="right")
            return
        self.widgets["phase"].set(self.T("更新失败", "Update failed"))
        self.widgets["retry_button"].pack(side="right")
        self.widgets["return_button"].pack(side="right", padx=(0, 8))
        self._append_log(message or self.T("更新失败，请重试。", "Update failed. Please retry."))

    def run_update(self) -> None:
        self._show_update_page(str(self.state.get("target") or ""))

        def worker() -> None:
            target = self.fetch_latest_version() or str(self.state.get("target") or "") or self.T("最新版本", "latest")
            try:
                if self.before_update is not None:
                    self.before_update()
                    self.root.after(0, lambda: self._append_log(self.T("已保存当前本地设置快照。", "Saved the current local settings snapshot.")))
                self.root.after(0, lambda: self.widgets["version"].set(f"Lucas {self.current_version}  →  {target}"))
                self.root.after(0, lambda: self._set_progress(8, "prepare"))
                script_path = Path(tempfile.gettempdir()) / "Lucas-Node-update.ps1"
                request = urllib.request.Request(
                    f"{self.installer_url}?t={int(time.time())}",
                    headers={"Cache-Control": "no-cache", "Pragma": "no-cache", "User-Agent": "Lucas-Node-Updater"},
                )
                with urllib.request.urlopen(request, timeout=30) as response:
                    script_path.write_bytes(response.read())
                self.root.after(0, lambda: self._set_progress(15, "runtime"))
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                process = subprocess.Popen(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(script_path),
                        "-UpdateFromApp",
                        "-KeepProcessId",
                        str(os.getpid()),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    errors="replace",
                    bufsize=1,
                    creationflags=flags,
                )
                if process.stdout is not None:
                    for raw in process.stdout:
                        line = raw.rstrip("\r\n")
                        if line.startswith("LUCAS_PROGRESS|"):
                            parts = line.split("|", 2)
                            if len(parts) == 3:
                                try:
                                    percent = int(parts[1])
                                except ValueError:
                                    percent = 0
                                self.root.after(0, lambda p=percent, s=parts[2]: self._set_progress(p, s))
                                continue
                        self.root.after(0, lambda value=line: self._append_log(value))
                code = process.wait()
                if code != 0:
                    raise RuntimeError(f"PowerShell updater exited with code {code}")
                self.root.after(0, lambda: self._finish_update(True, target))
            except Exception as exc:
                self.root.after(0, lambda err=str(exc): self._finish_update(False, target, err))

        threading.Thread(target=worker, daemon=True).start()

    def _check_update_worker(self) -> None:
        def set_checking() -> None:
            self.version_status.set(f"当前版本 {self.current_version} · 正在检查更新…")
            if self.check_update_button is not None:
                self.check_update_button.configure(state="disabled")
            if self.update_button is not None:
                self.update_button.configure(state="disabled")

        try:
            self.root.after(0, set_checking)
        except self.tk.TclError:
            return
        latest = self.fetch_latest_version()

        def apply_result() -> None:
            if self.check_update_button is not None:
                self.check_update_button.configure(state="normal")
            if not latest:
                self.version_status.set(f"当前版本 {self.current_version} · 无法检查更新")
                if self.update_button is not None:
                    self.update_button.configure(state="disabled")
                return
            if self.current_version != "dev" and self.version_key(latest) > self.version_key(self.current_version):
                self.version_status.set(f"当前版本 {self.current_version} · 新版本 {latest} 可用")
                self.state["target"] = latest
                if self.update_button is not None:
                    self.update_button.configure(state="normal")
            else:
                self.version_status.set(f"当前版本 {self.current_version} · 已是最新版本")
                if self.update_button is not None:
                    self.update_button.configure(state="disabled")

        try:
            self.root.after(0, apply_result)
        except self.tk.TclError:
            pass
