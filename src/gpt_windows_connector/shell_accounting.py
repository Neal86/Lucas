"""Shell operation accounting; never modifies executable commands."""
from __future__ import annotations

import re

_SHELL_STRUCTURAL = re.compile(
    r"^(?:if|elseif|else|foreach|for|while|switch|try|catch|finally|function|filter|class|param|begin|process|end|do)\b",
    re.IGNORECASE,
)
_SHELL_NON_ACTION = re.compile(
    r"^(?:return|break|continue|throw|exit|Write-(?:Host|Output|Verbose|Debug|Warning|Information)|Start-Sleep)\b",
    re.IGNORECASE,
)
_SHELL_NON_BILLABLE_COMMANDS = {
    "join-path", "split-path", "foreach-object", "where-object", "select-object",
    "sort-object", "group-object", "measure-object", "compare-object",
    "write-output", "write-host", "write-debug", "write-verbose", "write-warning",
    "write-information", "out-string", "format-table", "format-list", "format-wide",
    "format-custom", "convertto-json", "convertfrom-json", "convertto-csv",
    "convertfrom-csv", "get-date", "get-random", "start-sleep", "set-psdebug",
    "new-object", "set-variable", "get-variable", "out-null",
}
_SHELL_TRACE_RE = re.compile(r"^DEBUG:\s+(\d+)\+\s*.*?>>>>\s*(.*)$")


def _split_pipeline(text: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == quote and (i == 0 or text[i - 1] != "`"):
                quote = None
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch in "([": depth += 1
        elif ch in ")]": depth = max(0, depth - 1)
        if ch == "|" and depth == 0 and text[i:i+2] != "||":
            item = "".join(buf).strip()
            if item:
                out.append(item)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    item = "".join(buf).strip()
    if item:
        out.append(item)
    return out


def _billable_commands_from_statement(statement: str) -> list[str]:
    text = str(statement or "").strip()
    if not text:
        return []
    if text.startswith(("{", "}")):
        return []
    if "{" in text:
        text = text.split("{", 1)[0].strip()
    if not text or _SHELL_STRUCTURAL.match(text) or _SHELL_NON_ACTION.match(text):
        return []
    text = re.sub(r"\s*}\s*$", "", text).strip()
    assignment = re.match(r"^\$[A-Za-z_][\w:.-]*\s*(?:=|\+=|-=|\*=|/=)\s*(.+)$", text)
    if assignment:
        text = assignment.group(1).strip()
    labels: list[str] = []
    for stage in _split_pipeline(text):
        stage = stage.strip()
        if not stage:
            continue
        match = re.match(r"^(?:&\s*)?([A-Za-z][\w.-]*)\b", stage)
        if not match:
            continue
        command = match.group(1)
        if command.lower() in _SHELL_NON_BILLABLE_COMMANDS:
            continue
        labels.append(re.sub(r"\s+", " ", stage).strip()[:240])
    return labels


def _instrument_powershell(command: str) -> str:
    return "Set-PSDebug -Trace 1\ntry {\n" + str(command or "") + "\n} finally { Set-PSDebug -Off }"


def _source_operations_by_trace_line(command: str) -> dict[int, list[str]]:
    """Map Set-PSDebug trace line numbers back to billable commands in the user's script."""
    lines = str(command or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    mapping: dict[int, list[str]] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        trace_line = i + 3  # wrapper adds Set-PSDebug + try { before user code
        if stripped.startswith(("@'", '@"')):
            opener = stripped[:2]
            closer = "'@" if opener == "@'" else '"@'
            block = [line]
            j = i + 1
            while j < len(lines):
                block.append(lines[j])
                if closer in lines[j]:
                    break
                j += 1
            collapsed = "\n".join(block)
            collapsed = re.sub(r"@'(?s:.*?)'@", "'<here-string>'", collapsed)
            collapsed = re.sub(r'@"(?s:.*?)"@', '"<here-string>"', collapsed)
            ops = _billable_commands_from_statement(collapsed)
            if ops:
                mapping[trace_line] = ops
            i = j + 1
            continue
        ops = _billable_commands_from_statement(line)
        # One-line loop/conditional bodies need to be considered on the same source line.
        if "{" in line and "}" in line:
            inner = line.split("{", 1)[1].rsplit("}", 1)[0]
            for part in _split_shell_statements(inner):
                ops.extend(_billable_commands_from_statement(part))
        if ops:
            mapping[trace_line] = ops
        i += 1
    return mapping


def _extract_runtime_shell_operations(stdout: str, source_command: str = "") -> tuple[str, list[str]]:
    clean: list[str] = []
    actions: list[str] = []
    source_map = _source_operations_by_trace_line(source_command) if source_command else {}
    for line in str(stdout or "").splitlines(keepends=True):
        plain = line.rstrip("\r\n")
        match = _SHELL_TRACE_RE.match(plain)
        if not match:
            clean.append(line)
            continue
        trace_line = int(match.group(1))
        statement = match.group(2)
        allowed = source_map.get(trace_line)
        if source_map and not allowed:
            continue
        runtime = _billable_commands_from_statement(statement)
        if not runtime and allowed and statement.strip().startswith(("@'", '@"')):
            runtime = allowed
        if allowed:
            allowed_set = set(allowed)
            runtime = [op for op in runtime if op in allowed_set]
        actions.extend(runtime)
    return "".join(clean), actions


def _split_shell_statements(command: str) -> list[str]:
    """Split shell text on real statement separators, not separators inside quotes."""
    text = str(command or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    text = re.sub(r"@'(?s:.*?)'@", "'<here-string>'", text)
    text = re.sub(r'@"(?s:.*?)"@', '"<here-string>"', text)
    text = text.replace("`\n", " ")
    out: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    escaped = False
    i = 0
    while i < len(text):
        ch = text[i]
        if escaped:
            buf.append(ch); escaped = False; i += 1; continue
        if ch == "`" and quote == '"':
            buf.append(ch); escaped = True; i += 1; continue
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1; continue
        if ch in {"'", '"'}:
            quote = ch; buf.append(ch); i += 1; continue
        pair = text[i:i+2]
        if ch in {";", "\n"} or pair in {"&&", "||"}:
            item = "".join(buf).strip()
            if item:
                out.append(item)
            buf = []
            i += 2 if pair in {"&&", "||"} else 1
            continue
        buf.append(ch); i += 1
    item = "".join(buf).strip()
    if item:
        out.append(item)
    return out


def _shell_operations(command: str) -> list[str]:
    """Static fallback for shell accounting when runtime tracing is unavailable."""
    actions: list[str] = []
    for raw in _split_shell_statements(command):
        line = re.sub(r"^[{}()]+|[{}()]+$", "", raw.strip()).strip()
        if not line or line.startswith("#"):
            continue
        actions.extend(_billable_commands_from_statement(line))
    return actions or ["shell.run"]


def _shell_operation_count(command: str) -> int:
    return len(_shell_operations(command))


def _operation_count(method: str, params: dict | None = None) -> int:
    if method == "shell.run":
        return _shell_operation_count(str((params or {}).get("command") or ""))
    return 1

