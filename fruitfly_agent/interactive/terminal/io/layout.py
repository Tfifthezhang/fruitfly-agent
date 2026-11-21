"""Size and paint a generic two-column terminal frame."""
from __future__ import annotations

import os
from typing import TextIO

from .text import pad_cells, safe_terminal_text, truncate_cells, wrap_cells


def _single_line(text: str) -> str:
    return safe_terminal_text(text).replace('\n', ' ').replace('\t', ' ')


def terminal_size(output: TextIO) -> os.terminal_size:
    try:
        return os.get_terminal_size(output.fileno())
    except (AttributeError, OSError, ValueError):
        return os.terminal_size((80, 24))


def columns_frame(
    width: int, height: int, *, title: str, subtitle: str, left: tuple[str, ...],
    detail: str, footer: tuple[str, ...], detail_offset: int = 0,
) -> str:
    """Fit the rendered frame inside the given viewport."""
    left_width = max(24, width * 46 // 100)
    right_width = width - left_width - 4
    available = max(0, height - 3 - len(footer))
    details = [line for paragraph in detail.splitlines()
               for line in wrap_cells(_single_line(paragraph), right_width)]
    offset = min(detail_offset, max(0, len(details) - available))
    details = details[offset:offset + available]
    lines = [title, subtitle, '']
    for i in range(min(available, max(len(left), len(details)))):
        label = truncate_cells(_single_line(left[i]), left_width) if i < len(left) else ''
        lines.append(pad_cells(label, left_width) + ' │ ' + (details[i] if i < len(details) else ''))
    lines.extend(footer)
    return '\n'.join(truncate_cells(_single_line(line), width - 1) for line in lines)
