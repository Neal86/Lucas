from __future__ import annotations

import locale
import os
import sys


def system_language() -> str:
    """Return the Lucas UI language for this device: zh or en."""
    candidates: list[str] = []
    override = str(os.environ.get("LUCAS_LANGUAGE") or "").strip()
    if override:
        candidates.append(override)
    if sys.platform == "win32":
        try:
            import ctypes
            buffer = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
                candidates.append(buffer.value)
        except Exception:
            pass
    try:
        value = locale.getlocale()[0]
        if value:
            candidates.append(value)
    except Exception:
        pass
    candidates.extend([str(os.environ.get("LANG") or ""), str(os.environ.get("LANGUAGE") or "")])
    return "zh" if any(value.lower().replace("_", "-").startswith("zh") for value in candidates if value) else "en"


def tr(zh: str, en: str, language: str | None = None) -> str:
    return zh if (language or system_language()) == "zh" else en


def localize_tk_tree(root, translations: dict[str, str], language: str | None = None) -> None:
    """Translate existing Tk widget text and StringVar-backed text for English UI."""
    if (language or system_language()) != "en":
        return
    seen_vars: set[str] = set()
    stack = [root]
    while stack:
        widget = stack.pop()
        try:
            text = str(widget.cget("text"))
            if text in translations:
                widget.configure(text=translations[text])
        except Exception:
            pass
        try:
            variable = str(widget.cget("textvariable"))
            if variable and variable not in seen_vars:
                seen_vars.add(variable)
                value = str(root.getvar(variable))
                if value in translations:
                    root.setvar(variable, translations[value])
        except Exception:
            pass
        try:
            stack.extend(widget.winfo_children())
        except Exception:
            pass
