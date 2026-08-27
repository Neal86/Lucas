from __future__ import annotations

import ctypes
import ipaddress
import re
import threading
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


DEFAULT_SECURITY: dict[str, Any] = {
    "approval_policy": {
        "system_info": "allow",
        "shell": "allow",
        "file_write": "ask",
        "file_delete": "ask",
        "service_control": "ask",
        "high_risk": "always_ask",
    },
    "remember_approvals": True,
    "network_external": "ask",
    "network_lan": "allow",
    "allowed_domains": [],
    "block_silent_network": True,
    "rules_text": "所有安全策略以本机设置为准；网页端只能查看，不能修改本机权限与允许目录。",
    "show_rule_summary": True,
}


READ_METHODS = {
    "workspace.info", "workspace.browse", "files.list", "files.read", "files.search", "files.stat",
    "git.status", "git.diff", "git.log", "git.branch", "git.show", "process.poll", "process.list",
    "computer.info", "computer.processes", "computer.windows", "computer.screenshot", "computer.clipboard_get",
    "computer.ui_elements", "browser.discover", "browser.pages", "browser.inspect", "browser.screenshot",
}

FILE_WRITE_METHODS = {"files.write", "files.patch", "files.mkdir", "files.move", "files.copy"}
FILE_DELETE_METHODS = {"files.delete"}
NETWORK_METHODS = {"browser.navigate", "browser.new_page", "git.pull", "git.push"}

HIGH_RISK_PATTERNS = [
    r"\breg(?:\.exe)?\s+(?:add|delete)\b", r"\bbcdedit\b", r"\bdiskpart\b", r"\bformat(?:\.com)?\b",
    r"\bmanage-bde\b", r"\bnet\s+user\b", r"\bnet\s+localgroup\b", r"\bsc(?:\.exe)?\s+(?:delete|config)\b",
    r"\bSet-MpPreference\b", r"\bAdd-MpPreference\b", r"\bDisable-WindowsOptionalFeature\b",
    r"\bRemove-WindowsCapability\b", r"\bStop-Computer\b", r"\bRestart-Computer\b",
    r"Remove-Item[^\n]*(?:-Recurse|-Force)[^\n]*(?:Windows|Program Files|System32|Users\\)",
]
SERVICE_PATTERNS = [
    r"\b(?:Start|Stop|Restart|Set)-Service\b", r"\bsc(?:\.exe)?\s+(?:start|stop|pause|continue)\b",
    r"\bnet\s+(?:start|stop)\b",
]
NETWORK_COMMAND_PATTERNS = [
    r"\bInvoke-WebRequest\b", r"\bInvoke-RestMethod\b", r"\bcurl(?:\.exe)?\b", r"\bwget(?:\.exe)?\b",
    r"\bStart-BitsTransfer\b", r"\bgit\s+(?:clone|pull|push|fetch)\b", r"https?://",
]


def _merge_security(raw: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {**DEFAULT_SECURITY, "approval_policy": dict(DEFAULT_SECURITY["approval_policy"])}
    if isinstance(raw, dict):
        for key in ("remember_approvals", "network_external", "network_lan", "allowed_domains", "block_silent_network", "rules_text", "show_rule_summary"):
            if key in raw:
                merged[key] = raw[key]
        policy = raw.get("approval_policy")
        if isinstance(policy, dict):
            merged["approval_policy"].update({str(k): str(v) for k, v in policy.items()})
    return merged


def _command_text(method: str, params: dict[str, Any]) -> str:
    if method == "shell.run":
        return str(params.get("command") or "")
    if method == "process.start":
        return str(params.get("command") or params.get("target") or "")
    return ""


def _matches(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _extract_url(method: str, params: dict[str, Any]) -> str | None:
    if method == "browser.navigate":
        return str(params.get("url") or "").strip() or None
    text = _command_text(method, params)
    match = re.search(r"https?://[^\s\"']+", text, flags=re.IGNORECASE)
    return match.group(0) if match else None


def _is_lan_host(host: str) -> bool:
    normalized = host.strip("[]").lower()
    if normalized in {"localhost", "localhost.localdomain"} or normalized.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(normalized)
        return bool(ip.is_private or ip.is_loopback or ip.is_link_local)
    except ValueError:
        return False


def _host_allowed(host: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    host = host.lower().rstrip(".")
    for item in allowed:
        rule = str(item).strip().lower().rstrip(".")
        if not rule:
            continue
        if rule.startswith("*."):
            suffix = rule[1:]
            if host.endswith(suffix):
                return True
        elif host == rule or host.endswith("." + rule):
            return True
    return False


@dataclass
class LocalSecurityPolicy:
    config: dict[str, Any]
    _approved: set[str] = field(default_factory=set)
    _approval_lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.security = _merge_security(self.config.get("security"))

    def _category(self, method: str, params: dict[str, Any]) -> str:
        if method in READ_METHODS:
            return "system_info"
        if method in FILE_WRITE_METHODS:
            return "file_write"
        if method in FILE_DELETE_METHODS:
            return "file_delete"
        command = _command_text(method, params)
        if command and _matches(HIGH_RISK_PATTERNS, command):
            return "high_risk"
        if command and _matches(SERVICE_PATTERNS, command):
            return "service_control"
        if method in {"shell.run", "process.start"}:
            return "shell"
        if method in {"git.push"}:
            return "high_risk"
        return "shell"

    def _network_decision(self, method: str, params: dict[str, Any]) -> tuple[str, str] | None:
        command = _command_text(method, params)
        is_network = method in NETWORK_METHODS or (command and _matches(NETWORK_COMMAND_PATTERNS, command))
        if not is_network:
            return None
        url = _extract_url(method, params)
        if url:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            if host and not _host_allowed(host, [str(v) for v in self.security.get("allowed_domains", [])]):
                raise PermissionError(f"Network domain is not in the local allowlist: {host}")
            lan = _is_lan_host(host) if host else False
            return (str(self.security.get("network_lan" if lan else "network_external", "ask")), f"Network access to {host or url}")
        if self.security.get("block_silent_network", True):
            return ("ask", "Network-capable command without a detectable destination")
        return (str(self.security.get("network_external", "ask")), "Network-capable operation")

    def _approval_key(self, category: str, method: str, params: dict[str, Any], summary: str) -> str:
        command = _command_text(method, params).strip()
        if command:
            command = re.sub(r"\s+", " ", command)[:240]
        return f"{category}|{method}|{command or summary}"

    def _prompt(self, category: str, method: str, summary: str) -> bool:
        rules = str(self.security.get("rules_text") or "").strip()
        text = f"Lucas 请求在此电脑执行操作：\n\n{summary}\n\n方法：{method}\n风险类别：{category}"
        if self.security.get("show_rule_summary", True) and rules:
            text += f"\n\n本地规则：\n{rules[:700]}"
        text += "\n\n是否允许这次操作？"
        try:
            # MB_YESNO | MB_ICONWARNING | MB_TOPMOST | MB_SETFOREGROUND
            result = int(ctypes.windll.user32.MessageBoxW(None, text, "Lucas 安全确认", 0x00000004 | 0x00000030 | 0x00040000 | 0x00010000))
            return result == 6
        except Exception:
            return False

    def _enforce_decision(self, decision: str, category: str, method: str, params: dict[str, Any], summary: str) -> None:
        decision = str(decision or "ask").lower()
        if decision == "allow":
            return
        if decision == "block":
            raise PermissionError(f"Blocked by local Lucas security policy: {summary}")
        key = self._approval_key(category, method, params, summary)
        if decision != "always_ask" and self.security.get("remember_approvals", True) and key in self._approved:
            return
        with self._approval_lock:
            if decision != "always_ask" and self.security.get("remember_approvals", True) and key in self._approved:
                return
            if not self._prompt(category, method, summary):
                raise PermissionError(f"Denied locally: {summary}")
            if decision != "always_ask" and self.security.get("remember_approvals", True):
                self._approved.add(key)

    def authorize(self, method: str, params: dict[str, Any]) -> None:
        network = self._network_decision(method, params)
        if network:
            decision, summary = network
            self._enforce_decision(decision, "network", method, params, summary)
        category = self._category(method, params)
        decision = str(self.security.get("approval_policy", {}).get(category, "ask"))
        summary_map = {
            "system_info": "读取系统或项目状态",
            "shell": "运行命令或程序",
            "file_write": "创建或修改文件",
            "file_delete": "删除文件或目录",
            "service_control": "启动、停止或修改 Windows 服务",
            "high_risk": "执行高风险系统或发布操作",
        }
        self._enforce_decision(decision, category, method, params, summary_map.get(category, method))
