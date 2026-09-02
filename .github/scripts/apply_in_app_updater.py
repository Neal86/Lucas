from pathlib import Path
import textwrap

settings_path = Path("src/gpt_windows_connector/settings_ui.py")
settings = settings_path.read_text(encoding="utf-8")
if "\nimport sys\n" not in settings:
    settings = settings.replace("import subprocess\n", "import subprocess\nimport sys\n", 1)

start = settings.index('    current_version=_app_version(); version_status=')
end_marker = '    threading.Thread(target=check_update_worker,daemon=True).start()\n'
end = settings.index(end_marker, start) + len(end_marker)
replacement = r'''    current_version=_app_version(); version_status=tk.StringVar(value=f"当前版本 {current_version} · 正在检查更新…"); update_button=None; check_update_button=None; update_control=None
    update_state={"frame":None,"active":False,"return_page":"常规","success":False,"target":""}
    update_widgets={}
    update_stage_labels={
        "prepare":T("准备更新…","Preparing update…"),
        "runtime":T("检查运行环境…","Checking runtime…"),
        "install":T("下载并安装 Lucas…","Downloading and installing Lucas…"),
        "verify":T("验证新版本…","Verifying the new version…"),
        "startup":T("重新启动后台服务…","Restarting background services…"),
        "complete":T("更新完成","Update complete"),
    }
    def _append_update_log(line):
        widget=update_widgets.get("log")
        if widget is None or not widget.winfo_exists(): return
        widget.configure(state="normal"); widget.insert("end",line.rstrip()+"\n"); widget.configure(state="disabled"); widget.see("end")
    def _set_update_progress(percent,stage):
        progress=update_widgets.get("progress"); phase=update_widgets.get("phase")
        if progress is not None: progress.set(max(0,min(100,int(percent))))
        if phase is not None: phase.set(update_stage_labels.get(stage,stage))
    def _set_nav_enabled(enabled):
        for nav in nav_buttons.values():
            try: nav.configure(state=("normal" if enabled else "disabled"))
            except tk.TclError: pass
    def _show_update_page(target_version=""):
        if not update_state["active"]:
            update_state["return_page"]=_load_last_page()
        update_state["active"]=True; update_state["success"]=False; update_state["target"]=target_version or update_state.get("target") or ""
        for p in pages.values(): p.pack_forget()
        try: footer.pack_forget()
        except Exception: pass
        _set_nav_enabled(False)
        title.set(T("正在更新 Lucas","Updating Lucas")); subtitle.set(T("更新过程中请保持 Lucas 打开。完成后点击返回即可回到原界面。","Keep Lucas open during the update. When it finishes, use Return to go back."))
        frame=update_state.get("frame")
        if frame is None or not frame.winfo_exists():
            frame=tk.Frame(page_host,bg=C["window"]); update_state["frame"]=frame
            card_frame=tk.Frame(frame,bg=C["card"],highlightthickness=1,highlightbackground=C["line"]); card_frame.pack(fill="both",expand=True,pady=(8,14))
            top=tk.Frame(card_frame,bg=C["card"]); top.pack(fill="x",padx=24,pady=(22,10))
            version_var=tk.StringVar(value=""); update_widgets["version"]=version_var
            tk.Label(top,textvariable=version_var,font=(FONT,11,"bold"),fg=C["text"],bg=C["card"]).pack(anchor="w")
            phase=tk.StringVar(value=update_stage_labels["prepare"]); update_widgets["phase"]=phase
            tk.Label(top,textvariable=phase,font=(FONT,9),fg=C["muted"],bg=C["card"]).pack(anchor="w",pady=(5,0))
            progress=tk.IntVar(value=0); update_widgets["progress"]=progress
            ttk.Progressbar(card_frame,maximum=100,variable=progress,mode="determinate").pack(fill="x",padx=24,pady=(4,14))
            log=tk.Text(card_frame,height=20,font=("Consolas",9),bg="#111111",fg="#E6E6E6",insertbackground="#FFFFFF",relief="flat",bd=0,wrap="word",padx=10,pady=10,state="disabled"); log.pack(fill="both",expand=True,padx=24,pady=(0,14)); update_widgets["log"]=log
            actions=tk.Frame(card_frame,bg=C["card"]); actions.pack(fill="x",padx=24,pady=(0,20))
            return_btn=button(actions,T("返回","Return"),lambda: _leave_update_page(update_state.get("success",False)),primary=True); update_widgets["return_button"]=return_btn
            retry_btn=button(actions,T("重试更新","Retry update"),run_update); update_widgets["retry_button"]=retry_btn
        frame.pack(fill="both",expand=True)
        update_widgets["version"].set((f"Lucas {current_version}  →  {target_version}" if target_version else f"Lucas {current_version}"))
        log=update_widgets["log"]; log.configure(state="normal"); log.delete("1.0","end"); log.configure(state="disabled")
        for key in ("return_button","retry_button"):
            update_widgets[key].pack_forget()
        _set_update_progress(3,"prepare")
    def _leave_update_page(restart_after_update=False):
        update_state["active"]=False; frame=update_state.get("frame")
        if frame is not None and frame.winfo_exists(): frame.pack_forget()
        _set_nav_enabled(True)
        if restart_after_update:
            page=update_state.get("return_page") or "常规"; _save_last_page(page)
            env=os.environ.copy(); env["LUCAS_SETTINGS_PAGE"]=page
            flags=getattr(subprocess,"CREATE_NO_WINDOW",0)
            try: subprocess.Popen([sys.executable,"-m","gpt_windows_connector.node","--configure"],env=env,creationflags=flags)
            finally: root.destroy()
            return
        footer.pack(fill="x",side="bottom"); show_page(update_state.get("return_page") or "常规")
    def _finish_update(success,target_version,message=""):
        update_state["success"]=bool(success); update_state["target"]=target_version or update_state.get("target") or ""
        if success:
            _set_update_progress(100,"complete"); update_widgets["version"].set(T(f"Lucas 已更新至 {target_version}",f"Lucas has been updated to {target_version}")); update_widgets["return_button"].pack(side="right")
        else:
            update_widgets["phase"].set(T("更新失败","Update failed")); update_widgets["retry_button"].pack(side="right"); update_widgets["return_button"].pack(side="right",padx=(0,8)); _append_update_log(message or T("更新失败，请重试。","Update failed. Please retry."))
    def run_update():
        _show_update_page(update_state.get("target") or "")
        def worker():
            target=_fetch_latest_version() or update_state.get("target") or T("最新版本","latest")
            try:
                root.after(0,lambda: update_widgets["version"].set(f"Lucas {current_version}  →  {target}"))
                root.after(0,lambda: _set_update_progress(8,"prepare"))
                script_path=Path(tempfile.gettempdir())/"Lucas-Node-update.ps1"
                request=urllib.request.Request(f"{INSTALLER_URL}?t={int(time.time())}",headers={"Cache-Control":"no-cache","Pragma":"no-cache","User-Agent":"Lucas-Node-Updater"})
                with urllib.request.urlopen(request,timeout=30) as response: script_path.write_bytes(response.read())
                root.after(0,lambda: _set_update_progress(15,"runtime"))
                flags=getattr(subprocess,"CREATE_NO_WINDOW",0)|getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)
                process=subprocess.Popen(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(script_path),"-UpdateFromApp","-KeepProcessId",str(os.getpid())],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors="replace",bufsize=1,creationflags=flags)
                if process.stdout is not None:
                    for raw in process.stdout:
                        line=raw.rstrip("\r\n")
                        if line.startswith("LUCAS_PROGRESS|"):
                            parts=line.split("|",2)
                            if len(parts)==3:
                                try: percent=int(parts[1])
                                except ValueError: percent=0
                                root.after(0,lambda p=percent,s=parts[2]: _set_update_progress(p,s))
                                continue
                        root.after(0,lambda value=line: _append_update_log(value))
                code=process.wait()
                if code != 0: raise RuntimeError(f"PowerShell updater exited with code {code}")
                root.after(0,lambda: _finish_update(True,target))
            except Exception as exc:
                root.after(0,lambda err=str(exc): _finish_update(False,target,err))
        threading.Thread(target=worker,daemon=True).start()
    def check_update_worker(manual=False):
        def set_checking():
            version_status.set(f"当前版本 {current_version} · 正在检查更新…")
            if check_update_button is not None: check_update_button.configure(state="disabled")
            if update_button is not None: update_button.configure(state="disabled")
        try: root.after(0,set_checking)
        except tk.TclError: return
        latest=_fetch_latest_version()
        def apply_result():
            if check_update_button is not None: check_update_button.configure(state="normal")
            if not latest:
                version_status.set(f"当前版本 {current_version} · 无法检查更新")
                if update_button is not None: update_button.configure(state="disabled")
                return
            if current_version != "dev" and _version_key(latest)>_version_key(current_version):
                version_status.set(f"当前版本 {current_version} · 新版本 {latest} 可用"); update_state["target"]=latest
                if update_button is not None: update_button.configure(state="normal")
            else:
                version_status.set(f"当前版本 {current_version} · 已是最新版本")
                if update_button is not None: update_button.configure(state="disabled")
        try: root.after(0,apply_result)
        except tk.TclError: pass
    def start_update_check():
        threading.Thread(target=check_update_worker,args=(True,),daemon=True).start()
    def build_update_control(p):
        nonlocal update_button,check_update_button,update_control
        update_control=tk.Frame(p,bg=C["card"]); tk.Label(update_control,textvariable=version_status,font=(FONT,9,"bold"),fg=C["muted"],bg=C["card"]).pack(side="left"); check_update_button=button(update_control,"检测更新",start_update_check); check_update_button.pack(side="left",padx=(12,0)); update_button=button(update_control,"更新 Node",run_update,primary=True); update_button.pack(side="left",padx=(8,0)); update_button.configure(state="disabled"); return update_control
    row(c,"Lucas Node","自动检查新版本；也可手动检测并在有新版本时更新。",build_update_control)
    threading.Thread(target=check_update_worker,daemon=True).start()
'''
settings = settings[:start] + replacement + settings[end:]
settings_path.write_text(settings, encoding="utf-8")

installer_path = Path("scripts/install-node.ps1")
installer = installer_path.read_text(encoding="utf-8")
installer = installer.replace('[string]$InstallDir = "$env:LOCALAPPDATA\\Lucas"\n)', '[string]$InstallDir = "$env:LOCALAPPDATA\\Lucas",\n  [switch]$UpdateFromApp,\n  [int]$KeepProcessId = 0\n)', 1)
marker = '$ProgressPreference = "SilentlyContinue"\n'
if "function Write-LucasProgress" not in installer:
    installer = installer.replace(marker, marker + '\nfunction Write-LucasProgress {\n  param([int]$Percent, [string]$Stage)\n  if ($UpdateFromApp) { Write-Output ("LUCAS_PROGRESS|{0}|{1}" -f $Percent, $Stage) }\n}\n', 1)
installer = installer.replace('Write-Host ""\nWrite-Host "========================================" -ForegroundColor Cyan', 'Write-LucasProgress 5 "prepare"\nWrite-Host ""\nWrite-Host "========================================" -ForegroundColor Cyan', 1)
installer = installer.replace('Write-Host "[Lucas] Python runtime ready." -ForegroundColor Green', 'Write-Host "[Lucas] Python runtime ready." -ForegroundColor Green\nWrite-LucasProgress 20 "runtime"', 1)
installer = installer.replace('Where-Object {\n  $CommandLine = [string]$_.CommandLine\n  $CommandLine -and (', 'Where-Object {\n  $CommandLine = [string]$_.CommandLine\n  ($_.ProcessId -ne $KeepProcessId) -and $CommandLine -and (', 1)
package_start = installer.index('Write-Host "[Lucas] Installing the latest Lucas Node..." -ForegroundColor Yellow')
package_end = installer.index('$MachineGuid = ""', package_start)
package_block = '''Write-Host "[Lucas] Installing the latest Lucas Node..." -ForegroundColor Yellow
Write-LucasProgress 35 "install"
if (-not $UpdateFromApp) {
  & $VenvPython -m pip install --disable-pip-version-check --upgrade pip | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Failed to update pip." }
}

& $VenvPython -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('gpt_windows_connector') else 1)" 2>$null
$PackageAlreadyInstalled = ($LASTEXITCODE -eq 0)
$PackageUrl = "https://github.com/Neal86/Lucas/archive/refs/heads/main.zip"
if ($UpdateFromApp) {
  # In-app updates replace only Lucas itself. Existing dependencies stay in place,
  # preventing needless downloads and avoiding locked native dependency files.
  & $VenvPython -m pip install --disable-pip-version-check --force-reinstall --no-deps --no-cache-dir $PackageUrl
} elseif ($PackageAlreadyInstalled) {
  & $VenvPython -m pip install --disable-pip-version-check --force-reinstall --no-cache-dir $PackageUrl
} else {
  & $VenvPython -m pip install --disable-pip-version-check --no-cache-dir $PackageUrl
}
if ($LASTEXITCODE -ne 0) { throw "Failed to install the latest Lucas Node." }

$InstalledVersion = (& $VenvPython -c "import importlib.metadata; print(importlib.metadata.version('gpt-windows-connector'))").Trim()
if ([string]::IsNullOrWhiteSpace($InstalledVersion)) { throw "Lucas Node installation verification failed." }
Write-Host "[Lucas] Installed Lucas Node $InstalledVersion" -ForegroundColor Green
Write-LucasProgress 75 "verify"

'''
installer = installer[:package_start] + package_block + installer[package_end:]
installer = installer.replace('Write-Host "[Lucas] Installing background startup..." -ForegroundColor Green', 'Write-LucasProgress 85 "startup"\nWrite-Host "[Lucas] Installing background startup..." -ForegroundColor Green', 1)
old_open = '''# Installation always finishes by opening the Lucas app (Settings). The tray and
# node are already running in the background; Settings is the visible app surface.
Write-Host "[Lucas] Opening Lucas..." -ForegroundColor Cyan
Start-Process -FilePath $VenvPythonw -ArgumentList "-m","gpt_windows_connector.node","--configure" -WindowStyle Hidden

Write-Host ""
Write-Host "[Lucas] Installed successfully." -ForegroundColor Green'''
new_open = '''# Fresh installs open Settings. During an in-app update the existing Settings
# window stays alive to show progress, then restarts itself when the user returns.
if (-not $UpdateFromApp) {
  Write-Host "[Lucas] Opening Lucas..." -ForegroundColor Cyan
  Start-Process -FilePath $VenvPythonw -ArgumentList "-m","gpt_windows_connector.node","--configure" -WindowStyle Hidden
} else {
  Write-Host "[Lucas] App update finished; waiting for Settings to restart itself." -ForegroundColor Green
}
Write-LucasProgress 100 "complete"

Write-Host ""
Write-Host "[Lucas] Installed successfully." -ForegroundColor Green'''
if old_open not in installer:
    raise SystemExit("installer opening block changed unexpectedly")
installer = installer.replace(old_open, new_open, 1)
installer_path.write_text(installer, encoding="utf-8")

test_path = Path("tests/test_update_ui_contract.py")
test_path.write_text(textwrap.dedent('''
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_settings_update_stays_inside_app_and_hides_console():
    text = (ROOT / "src/gpt_windows_connector/settings_ui.py").read_text(encoding="utf-8")
    assert "CREATE_NO_WINDOW" in text
    assert '"-UpdateFromApp"' in text
    assert "LUCAS_PROGRESS|" in text
    assert "root.after(300,root.destroy)" not in text
    assert 'title.set(T("正在更新 Lucas","Updating Lucas"))' in text
    assert 'update_widgets["return_button"]' in text

def test_installer_has_fast_in_app_update_mode():
    text = (ROOT / "scripts/install-node.ps1").read_text(encoding="utf-8")
    assert "[switch]$UpdateFromApp" in text
    assert "[int]$KeepProcessId = 0" in text
    assert "--force-reinstall --no-deps --no-cache-dir" in text
    assert 'Write-LucasProgress 100 "complete"' in text
    assert '($_.ProcessId -ne $KeepProcessId)' in text
''').lstrip(), encoding="utf-8")
