from __future__ import annotations

import re


_FORMAT_EXE = r"(?:format(?:\.com)?)"
_VOLUME_TARGET = r"(?:[A-Za-z]:|\\\\\?\\Volume\{[0-9A-Fa-f-]+\}\\?)"


def _split_command_segments(command: str) -> list[str]:
    """Split shell command separators while ignoring separators inside quotes."""
    text = str(command or "")
    segments: list[str] = []
    current: list[str] = []
    quote = ""
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            current.append(ch)
            if ch == quote:
                quote = ""
            elif ch == "\\" and i + 1 < len(text):
                i += 1
                current.append(text[i])
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            current.append(ch)
            i += 1
            continue
        if ch in {"\r", "\n", ";"}:
            segment = "".join(current).strip()
            if segment:
                segments.append(segment)
            current = []
            i += 1
            continue
        if ch in {"&", "|"} and i + 1 < len(text) and text[i + 1] == ch:
            segment = "".join(current).strip()
            if segment:
                segments.append(segment)
            current = []
            i += 2
            continue
        current.append(ch)
        i += 1
    segment = "".join(current).strip()
    if segment:
        segments.append(segment)
    return segments


def _strip_outer_quotes(text: str) -> str:
    value = str(text or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def _segment_invokes_format(segment: str) -> bool:
    value = str(segment or "").strip()
    if not value:
        return False

    direct = rf"^(?:&\s*)?[\"']?{_FORMAT_EXE}[\"']?\s+{_VOLUME_TARGET}(?:\s|$)"
    if re.search(direct, value, flags=re.IGNORECASE):
        return True

    cmd_wrapper = re.match(r"^cmd(?:\.exe)?\s+/[ck]\s+(.+)$", value, flags=re.IGNORECASE)
    if cmd_wrapper:
        return is_disk_format_command(_strip_outer_quotes(cmd_wrapper.group(1)))

    ps_wrapper = re.match(
        r"^(?:powershell|pwsh)(?:\.exe)?\b.*?(?:-Command|-c)\s+(.+)$",
        value,
        flags=re.IGNORECASE,
    )
    if ps_wrapper:
        return is_disk_format_command(_strip_outer_quotes(ps_wrapper.group(1)))

    return False


def is_disk_format_command(command: str) -> bool:
    """Return True only when the shell text actually invokes Windows disk format."""
    return any(_segment_invokes_format(segment) for segment in _split_command_segments(command))
