"""Render read-only command panels without knowing the originating command."""
from __future__ import annotations

from fruitfly_agent.interactive.contracts.commands import CommandPanel
from fruitfly_agent.interactive.terminal.io.text import (
    cell_width, pad_cells, safe_terminal_text, truncate_cells,
)


# Each title sets both foreground and background for light/dark terminal palettes.
_SECTION_STYLES = {
    "context-manager": "\x1b[1;37;44m",
    "environment": "\x1b[1;30;46m",
    "tools": "\x1b[1;37;45m",
    "workflow": "\x1b[1;37;44m",
    "improvement": "\x1b[1;30;43m",
}


def _plain(text: str) -> str:
    return " ".join(safe_terminal_text(text).split())


def _wrap(text: str, width: int) -> list[str]:
    remaining = _plain(text)
    lines = []
    while cell_width(remaining) > width:
        prefix = truncate_cells(remaining, width, ellipsis="")
        boundary = prefix.rfind(" ")
        if boundary > 0:
            prefix = prefix[:boundary]
        lines.append(prefix)
        remaining = remaining[len(prefix):].lstrip()
    return [*lines, remaining]


def render_command_panel(panel: CommandPanel, *, columns: int = 80, color: bool = False) -> str:
    """Keep all row text, wrapping into stacked rows on narrow terminals."""
    width = max(4, columns - 1)
    title = truncate_cells(_plain(panel.title), width)
    lines = [f"\x1b[1m{title}\x1b[0m" if color else title, ""]
    for section in panel.sections:
        heading = truncate_cells(" " + _plain(section.title) + " ", width)
        style = _SECTION_STYLES.get(section.category, "\x1b[1;37;44m")
        lines.append(f"{style}{heading}\x1b[0m" if color else heading.strip())
        label_width = min(24, max((cell_width(_plain(label)) for label, _ in section.rows), default=0))
        for label, value in section.rows:
            label, value = _plain(label), _plain(value)
            if width < 52 or cell_width(label) > label_width:
                lines.extend("  " + line for line in _wrap(label, width - 2))
                indent = min(4, width - 2)
                lines.extend(" " * indent + line for line in _wrap(value, width - indent))
            else:
                continuation = " " * (label_width + 4)
                wrapped = _wrap(value, width - label_width - 4)
                lines.append("  " + pad_cells(label, label_width) + "  " + wrapped[0])
                lines.extend(continuation + line for line in wrapped[1:])
        lines.append("")
    if panel.footer:
        for line in _wrap(panel.footer, width):
            lines.append(f"\x1b[2m{line}\x1b[0m" if color else line)
    return "\n".join(lines) + "\n"
