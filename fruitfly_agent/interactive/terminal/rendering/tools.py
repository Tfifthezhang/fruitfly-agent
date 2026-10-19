"""Bounded, safe tool metadata shared by transcript and detail views."""

import json
import re
from fruitfly_agent.interactive.terminal.io.text import safe_terminal_text, truncate_cells

_TOOL_ARGUMENT_CELLS = 240
_SENSITIVE_ARGUMENT = re.compile(
    r"(?:api[_-]?key|authorization|cookie|password|secret|token)",
    re.IGNORECASE,
)
_ARGUMENT_PRIORITY = {
    "path": 0,
    "command": 1,
    "query": 2,
    "pattern": 3,
    "name": 4,
    "id": 5,
}


def summarize_arguments(arguments: dict[str, object]) -> str:
    """Render bounded metadata without dumping source files or secrets."""

    if not arguments:
        return "{}"
    ordered = sorted(
        arguments.items(),
        key=lambda item: (_ARGUMENT_PRIORITY.get(item[0].casefold(), 100), item[0]),
    )
    parts = [f"{key}={_summarize_value(key, value)}" for key, value in ordered]
    return truncate_cells(safe_terminal_text(" · ".join(parts)), _TOOL_ARGUMENT_CELLS)


def _summarize_value(key: str, value: object) -> str:
    if _SENSITIVE_ARGUMENT.search(key):
        return "<redacted>"
    if isinstance(value, str):
        lines = value.count("\n") + 1
        if len(value) > 120 or lines > 1:
            return f"<{len(value):,} chars, {lines:,} lines>"
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return f"<{len(value):,} fields>"
    if isinstance(value, (list, tuple)):
        return f"<{len(value):,} items>"
    return json.dumps(value, ensure_ascii=False, default=repr)


def summarize_result(output: str) -> str:
    stripped = output.strip()
    if not stripped:
        return ""
    lines = stripped.count("\n") + 1
    if len(stripped) > 500 or lines > 3:
        return f"<{len(stripped):,} chars, {lines:,} lines>"
    return truncate_cells(" ".join(safe_terminal_text(stripped).split()), _TOOL_ARGUMENT_CELLS)

