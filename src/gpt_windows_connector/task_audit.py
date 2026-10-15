"""Privacy boundary for persisted and displayed task-operation details."""

from __future__ import annotations

from typing import Any


def sanitize_task_details(details: Any) -> dict[str, Any]:
    """Copy audit metadata without retaining shell sub-operation content.

    Shell accounting needs full statements internally, but task history only needs
    their number. A fixed label avoids guessing which commands, arguments, paths,
    or values are sensitive. Preserve the string-array contract and cardinality;
    never derive or change the separately recorded operation_count here.

    The same projection protects legacy rows when read, without rewriting them.
    Other metadata is preserved; this is not a general-purpose secret scrubber.
    """
    if not isinstance(details, dict):
        return {}
    sanitized = dict(details)
    if "sub_operations" in sanitized:
        operations = sanitized["sub_operations"]
        sanitized["sub_operations"] = (
            ["shell.run"] * len(operations)
            if isinstance(operations, (list, tuple))
            else []
        )
    return sanitized
