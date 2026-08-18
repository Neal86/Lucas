from __future__ import annotations

import base64
import io
import json
import subprocess
import time

CREATE_NO_WINDOW = 0x08000000


def _ps(command: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=CREATE_NO_WINDOW, shell=False,
    )


def list_processes(limit: int = 100) -> list[dict]:
    command = "Get-Process | Sort-Object CPU -Descending | Select-Object -First %d Id,ProcessName,MainWindowTitle,Path | ConvertTo-Json -Compress" % max(1, min(limit, 500))
    completed = _ps(command)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Unable to list processes")
    raw = completed.stdout.strip()
    if not raw:
        return []
    data = json.loads(raw)
    return data if isinstance(data, list) else [data]


def launch_app(target: str, arguments: str = "") -> dict:
    safe_target = target.replace("'", "''")
    safe_args = arguments.replace("'", "''")
    command = f"$p = Start-Process -FilePath '{safe_target}'"
    if arguments:
        command += f" -ArgumentList '{safe_args}'"
    command += " -PassThru; $p | Select-Object Id,ProcessName | ConvertTo-Json -Compress"
    completed = _ps(command)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"Unable to launch {target}")
    return json.loads(completed.stdout)


def system_info() -> dict:
    command = "$os=Get-CimInstance Win32_OperatingSystem;$cs=Get-CimInstance Win32_ComputerSystem;[pscustomobject]@{ComputerName=$env:COMPUTERNAME;UserName=$env:USERNAME;Windows=$os.Caption;Version=$os.Version;Architecture=$os.OSArchitecture;RAMBytes=$cs.TotalPhysicalMemory} | ConvertTo-Json -Compress"
    completed = _ps(command)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Unable to get system information")
    return json.loads(completed.stdout)


def _gui():
    import pyautogui
    pyautogui.PAUSE = 0.05
    return pyautogui


def screenshot() -> dict:
    image = _gui().screenshot()
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return {"mime_type": "image/png", "base64": base64.b64encode(buf.getvalue()).decode("ascii"), "width": image.width, "height": image.height}


def click(x: int, y: int, button: str = "left", clicks: int = 1) -> dict:
    _gui().click(x=x, y=y, button=button, clicks=clicks)
    return {"x": x, "y": y, "button": button, "clicks": clicks}


def move(x: int, y: int, duration: float = 0.0) -> dict:
    _gui().moveTo(x, y, duration=max(0.0, duration))
    return {"x": x, "y": y}


def drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.2, button: str = "left") -> dict:
    gui = _gui(); gui.moveTo(x1, y1); gui.dragTo(x2, y2, duration=max(0.0, duration), button=button)
    return {"from": [x1, y1], "to": [x2, y2]}


def type_text(text: str, interval: float = 0.0) -> dict:
    gui = _gui()
    if text.isascii():
        gui.write(text, interval=max(0.0, interval))
        mode = "keyboard"
    else:
        import pyperclip
        previous = pyperclip.paste()
        try:
            pyperclip.copy(text)
            gui.hotkey("ctrl", "v")
            time.sleep(0.08)
        finally:
            pyperclip.copy(previous)
        mode = "clipboard"
    return {"characters": len(text), "mode": mode}


def hotkey(keys: list[str]) -> dict:
    _gui().hotkey(*keys)
    return {"keys": keys}


def press(key: str, presses: int = 1) -> dict:
    _gui().press(key, presses=max(1, presses))
    return {"key": key, "presses": presses}


def scroll(amount: int, x: int | None = None, y: int | None = None) -> dict:
    if x is not None and y is not None:
        _gui().moveTo(x, y)
    _gui().scroll(amount)
    return {"amount": amount}


def clipboard_get() -> str:
    import pyperclip
    return pyperclip.paste()


def clipboard_set(text: str) -> dict:
    import pyperclip
    pyperclip.copy(text)
    return {"characters": len(text)}


def list_windows() -> list[dict]:
    from pywinauto import Desktop
    out = []
    for window in Desktop(backend="uia").windows():
        try:
            rect = window.rectangle()
            out.append({"title": window.window_text(), "handle": int(window.handle), "rect": [rect.left, rect.top, rect.right, rect.bottom]})
        except Exception:
            continue
    return out


def activate_window(title_re: str) -> dict:
    from pywinauto import Desktop
    window = Desktop(backend="uia").window(title_re=title_re)
    window.set_focus()
    return {"title": window.window_text(), "handle": int(window.handle)}


def ui_elements(title_re: str | None = None, limit: int = 500) -> list[dict]:
    from pywinauto import Desktop
    desktop = Desktop(backend="uia")
    roots = [desktop.window(title_re=title_re)] if title_re else desktop.windows()
    out: list[dict] = []
    for root in roots:
        try:
            elements = [root, *root.descendants()]
        except Exception:
            continue
        for element in elements:
            try:
                info = element.element_info
                rect = element.rectangle()
                out.append({
                    "name": element.window_text(),
                    "control_type": getattr(info, "control_type", None),
                    "automation_id": getattr(info, "automation_id", None),
                    "class_name": getattr(info, "class_name", None),
                    "handle": int(element.handle) if element.handle else None,
                    "rect": [rect.left, rect.top, rect.right, rect.bottom],
                    "enabled": element.is_enabled(),
                    "visible": element.is_visible(),
                })
            except Exception:
                continue
            if len(out) >= max(1, min(limit, 5000)):
                return out
    return out


def _find_element(title_re: str, name: str | None = None, automation_id: str | None = None, control_type: str | None = None):
    from pywinauto import Desktop
    window = Desktop(backend="uia").window(title_re=title_re)
    kwargs = {}
    if name is not None:
        kwargs["title"] = name
    if automation_id is not None:
        kwargs["auto_id"] = automation_id
    if control_type is not None:
        kwargs["control_type"] = control_type
    if not kwargs:
        raise ValueError("At least one of name, automation_id, or control_type is required")
    return window.child_window(**kwargs).wrapper_object()


def ui_click(title_re: str, name: str | None = None, automation_id: str | None = None, control_type: str | None = None) -> dict:
    element = _find_element(title_re, name, automation_id, control_type)
    try:
        element.invoke()
        mode = "invoke"
    except Exception:
        element.click_input()
        mode = "click_input"
    return {"name": element.window_text(), "mode": mode}


def ui_set_text(title_re: str, text: str, name: str | None = None, automation_id: str | None = None, control_type: str | None = None) -> dict:
    element = _find_element(title_re, name, automation_id, control_type)
    element.set_focus()
    try:
        element.set_edit_text(text)
        mode = "set_edit_text"
    except Exception:
        element.click_input()
        hotkey(["ctrl", "a"])
        type_text(text)
        mode = "keyboard"
    return {"name": element.window_text(), "characters": len(text), "mode": mode}
