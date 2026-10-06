"""Small terminal text primitives shared by built-in frontend pieces."""

from __future__ import annotations

import os
import unicodedata
from typing import TextIO


def is_tty(stream: TextIO) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, OSError):
        return False


def supports_ansi(stream: TextIO) -> bool:
    """Return whether local cursor/color sequences are appropriate."""
    return is_tty(stream) and os.environ.get("TERM", "").lower() != "dumb"


def colors_enabled(stream: TextIO) -> bool:
    return supports_ansi(stream) and "NO_COLOR" not in os.environ


def terminal_columns(stream: TextIO, *, fallback: int = 80) -> int:
    try:
        columns = os.get_terminal_size(stream.fileno()).columns
    except (AttributeError, OSError, ValueError):
        return fallback
    return columns if columns >= 4 else fallback


def cell_width(text: str) -> int:
    """Approximate terminal cells using only Unicode standard-library data."""
    width = 0
    for char in text:
        if char in {"\u200d", "\ufe0e", "\ufe0f"}:
            continue
        if unicodedata.combining(char) or unicodedata.category(char).startswith("C"):
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
    return width


def truncate_cells(text: str, limit: int, *, ellipsis: str = "…") -> str:
    """Truncate text to a terminal-cell budget without splitting code points."""
    if limit <= 0:
        return ""
    if cell_width(text) <= limit:
        return text
    ellipsis_width = cell_width(ellipsis)
    if ellipsis_width > limit:
        return ""
    budget = limit - ellipsis_width
    result: list[str] = []
    used = 0
    for char in text:
        char_width = cell_width(char)
        if used + char_width > budget:
            break
        result.append(char)
        used += char_width
    return "".join(result).rstrip() + ellipsis


def pad_cells(text: str, width: int) -> str:
    return text + (" " * max(0, width - cell_width(text)))


__all__ = [
    "cell_width",
    "colors_enabled",
    "is_tty",
    "pad_cells",
    "supports_ansi",
    "terminal_columns",
    "truncate_cells",
]
