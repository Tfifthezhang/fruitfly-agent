"""Shared truncation utilities for Lab tool outputs.

Dual independent limits, whichever is hit first wins:
- line limit (default 2000 lines)
- byte limit (default 50KB)

Keeps complete lines where possible; an oversized edge line is clipped at a
UTF-8 character boundary so the byte limit remains a hard bound.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MAX_LINES = 2000
DEFAULT_MAX_BYTES = 50 * 1024


@dataclass(frozen=True)
class TruncationResult:
    content: str
    truncated: bool
    truncated_by: str | None  # "lines" | "bytes" | None
    total_lines: int
    total_bytes: int
    output_lines: int
    output_bytes: int


def _line_count(content: str) -> int:
    if not content:
        return 0
    lines = content.split("\n")
    if content.endswith("\n"):
        lines.pop()
    return len(lines)


def _truncate(content: str, max_lines: int, max_bytes: int, *, tail: bool) -> TruncationResult:
    for name, value in (("max_lines", max_lines), ("max_bytes", max_bytes)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    total_lines = _line_count(content)
    total_bytes = len(content.encode("utf-8"))
    lines = content.split("\n") if content else []
    trailing_newline = content.endswith("\n")
    if trailing_newline:
        lines.pop()
    by_lines = total_lines > max_lines
    if max_lines == 0:
        kept = []
    elif by_lines:
        kept = lines[-max_lines:] if tail else lines[:max_lines]
    else:
        kept = lines
    text = "\n".join(kept)
    if kept and trailing_newline and (tail or not by_lines):
        text += "\n"
    reason = "lines" if by_lines else None
    encoded = text.encode("utf-8")
    if len(encoded) > max_bytes:
        clipped = (encoded[-max_bytes:] if tail else encoded[:max_bytes]) if max_bytes else b""
        text = clipped.decode("utf-8", errors="ignore")
        # Prefer complete lines. If no nonempty complete edge line fits, retain
        # the clipped oversized line instead of returning only a trailing newline.
        boundary = text.find("\n") if tail else text.rfind("\n")
        if boundary >= 0:
            complete = text[boundary + 1:] if tail else text[:boundary]
            if complete:
                text = complete
        reason = "bytes"
    return TruncationResult(
        content=text, truncated=reason is not None, truncated_by=reason,
        total_lines=total_lines, total_bytes=total_bytes,
        output_lines=_line_count(text), output_bytes=len(text.encode("utf-8")),
    )


def truncate_tail(
    content: str, max_lines: int = DEFAULT_MAX_LINES, max_bytes: int = DEFAULT_MAX_BYTES
) -> TruncationResult:
    """Keep the last lines/bytes, clipping oversized edge lines safely."""
    return _truncate(content, max_lines, max_bytes, tail=True)


def truncate_head(
    content: str, max_lines: int = DEFAULT_MAX_LINES, max_bytes: int = DEFAULT_MAX_BYTES
) -> TruncationResult:
    """Keep the first lines/bytes, clipping oversized edge lines safely."""
    return _truncate(content, max_lines, max_bytes, tail=False)
