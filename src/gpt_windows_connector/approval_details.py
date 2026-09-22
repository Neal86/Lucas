from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


_SECRET_PATTERNS = (
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s;]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b(api[_-]?key|token|password|passwd|secret|client[_-]?secret)\s*[:=]\s*(['\"]?)[^\s;'\"]+\2"), r"\1=[REDACTED]"),
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"(?i)([?&](?:token|api[_-]?key|key|secret|password)=)[^&#\s]+"), r"\1[REDACTED]"),
)


def _command_text(method: str, params: dict[str, Any]) -> str:
    if method == "shell.run":
        return str(params.get("command") or "")
    if method == "process.start":
        return str(params.get("command") or params.get("target") or "")
    return ""


def safe_command_preview(method: str, params: dict[str, Any], *, limit: int = 700) -> str:
    text = _command_text(method, params)
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    if len(text) > limit:
        text = text[: max(0, limit - 1)].rstrip() + "…"
    return text


def _first_url(command: str) -> str:
    match = re.search(r"https?://[^\s\"']+", command, flags=re.IGNORECASE)
    return match.group(0).rstrip(");,") if match else ""


def _host_from_command(command: str) -> str:
    url = _first_url(command)
    if not url:
        return ""
    try:
        return str(urlparse(url).hostname or "")
    except Exception:
        return ""


def _high_risk_operation(command: str) -> tuple[str, str] | None:
    checks: tuple[tuple[str, str, str], ...] = (
        (r"\bRestart-Computer\b", "重启这台电脑", "命令会重启 Windows，当前应用和连接会被中断"),
        (r"\bStop-Computer\b", "关闭这台电脑", "命令会关闭 Windows"),
        (r"\bbcdedit\b", "修改 Windows 启动配置", "命令会修改系统启动/引导配置"),
        (r"\bdiskpart\b", "修改磁盘或分区", "命令会调用磁盘分区管理工具"),
        (r"\bformat(?:\.com)?\b", "格式化磁盘或卷", "格式化可能导致目标卷数据丢失"),
        (r"\bmanage-bde\b", "修改 BitLocker 设置", "命令会修改磁盘加密配置"),
        (r"\bnet\s+user\b", "修改 Windows 用户账户", "命令会创建、删除或修改本地用户"),
        (r"\bnet\s+localgroup\b", "修改 Windows 用户组", "命令会修改本地用户组成员或权限"),
        (r"\bsc(?:\.exe)?\s+(?:delete|config)\b", "修改 Windows 服务配置", "命令会删除或重新配置系统服务"),
        (r"\bSet-MpPreference\b|\bAdd-MpPreference\b", "修改 Microsoft Defender 设置", "命令会修改 Windows 安全防护配置"),
        (r"\bDisable-WindowsOptionalFeature\b|\bRemove-WindowsCapability\b", "修改 Windows 系统组件", "命令会禁用或移除 Windows 组件"),
        (r"\breg(?:\.exe)?\s+(?:add|delete|import)\b|\bSet-ItemProperty\b[^\n]*(?:HKLM:|HKCU:|Registry::)", "修改 Windows 注册表", "命令会写入或删除注册表设置"),
    )
    for pattern, operation, reason in checks:
        if re.search(pattern, command, flags=re.IGNORECASE):
            return operation, reason
    if re.search(r"\bRemove-Item\b", command, flags=re.IGNORECASE) and re.search(r"-(?:Recurse|Force)\b", command, flags=re.IGNORECASE):
        if re.search(r"(?i)(?:[A-Z]:\\)?(?:Windows|Program Files(?: \(x86\))?|ProgramData)(?:\\|[\"'\s;]|$)", command):
            return "递归/强制删除系统目录", "目标包含 Windows 或 Program Files 等系统目录"
        if re.search(r"(?i)[A-Z]:\\Users(?:\\)?(?=[\"'\s;]|$)|[A-Z]:\\Users\\\*(?=[\"'\s;]|$)", command):
            return "递归/强制删除 Windows 用户根目录", "目标是 C:\\Users 根目录或其全部用户目录"
        if re.search(r"(?i)[A-Z]:\\Users\\[^\\\s\"']+(?=[\"'\s;]|$)", command):
            return "递归/强制删除整个用户配置目录", "目标看起来是完整的 Windows 用户目录")
        if re.search(r"(?i)\$env:(?:USERPROFILE|SystemRoot|windir)(?:\\)?(?=[\"'\s;]|$)", command):
            return "递归/强制删除用户或系统根目录", "目标使用 USERPROFILE/SystemRoot 等敏感系统路径")
    return None


def describe_approval(category: str, method: str, params: dict[str, Any], audit_context: dict[str, Any] | None = None) -> dict[str, str]:
    context = dict(audit_context or {})
    command = _command_text(method, params)
    preview = safe_command_preview(method, params)
    workspace = str(params.get("workspace") or "")
    task_title = str(context.get("task_title") or "").strip()

    operation = ""
    risk_reason = ""
    high_risk = _high_risk_operation(command)
    if high_risk:
        operation, risk_reason = high_risk

    if not operation:
        if method == "shell.run":
            host = _host_from_command(command)
            if re.search(r"\b(?:Invoke-WebRequest|Invoke-RestMethod|curl(?:\.exe)?|wget(?:\.exe)?)\b", command, flags=re.IGNORECASE):
                operation = f"访问或检查网络地址{f'（{host}）' if host else ''}"
                risk_reason = "命令会访问网络"
            elif re.search(r"\bgit\s+push\b", command, flags=re.IGNORECASE):
                operation = "向 Git 远端推送代码"
                risk_reason = "会修改远端 Git 仓库"
            elif re.search(r"\bgit\s+(?:pull|fetch|clone)\b", command, flags=re.IGNORECASE):
                operation = "读取或同步 Git 仓库"
                risk_reason = "命令会访问 Git 远端"
            elif re.search(r"\b(?:pytest|npm\s+test|npm\s+run\s+test|cargo\s+test)\b", command, flags=re.IGNORECASE):
                operation = "运行项目测试"
                risk_reason = "命令会在本机执行项目代码"
            elif re.search(r"\b(?:pip|python\s+-m\s+pip)\s+install\b|\bnpm\s+(?:install|ci)\b|\bwinget\s+install\b", command, flags=re.IGNORECASE):
                operation = "安装项目或软件依赖"
                risk_reason = "命令会安装或修改本机软件/依赖"
            elif re.search(r"\bRemove-Item\b", command, flags=re.IGNORECASE):
                operation = "删除指定文件或目录"
                risk_reason = "命令包含文件删除操作"
            else:
                operation = "运行 PowerShell 命令"
                risk_reason = "请求会在本机执行命令"
        else:
            labels = {
                "files.write": "创建或修改文件",
                "files.patch": "修改文件内容",
                "files.delete": "删除文件或目录",
                "process.start": "启动程序或进程",
                "process.stop": "停止进程",
                "git.push": "向 Git 远端推送代码",
                "computer.activate": "切换到指定窗口",
                "computer.type": "向前台窗口输入文字",
                "computer.click": "点击桌面界面",
                "browser.navigate": "打开网页",
                "browser.upload": "上传文件到网页",
                "browser.download": "从网页下载文件",
            }
            operation = labels.get(method, method)
            risk_reason = "此操作受本机 Lucas 安全策略保护"

    if task_title:
        purpose = f"任务：{task_title}"
    elif workspace:
        purpose = f"在 {workspace} 中执行上述操作；请求未携带任务标题"
    else:
        purpose = "请求未携带任务标题，请根据操作与命令确认是否符合你的预期"

    return {
        "operation": operation,
        "purpose": purpose,
        "risk_reason": risk_reason,
        "workspace": workspace,
        "command_preview": preview,
    }
