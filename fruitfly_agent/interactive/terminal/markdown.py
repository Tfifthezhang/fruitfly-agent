"""Streaming Markdown presentation for the built-in ANSI terminal.

The model/session representation remains untouched.  This module receives a
presentation-only copy of assistant text, parses complete CommonMark blocks and
returns ANSI-safe terminal text plus a replaceable preview for the unfinished
tail.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import time
import unicodedata
from typing import Sequence

from markdown_it import MarkdownIt
from markdown_it.token import Token
from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

from .text import cell_width, pad_cells, truncate_cells


_RESET = "\033[0m"
_CONTROL_ESCAPE = re.compile(
    r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|[78])"
)
_SGR_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
_ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(?:\s|$)")
_HORIZONTAL_RULE = re.compile(
    r"^ {0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$"
)
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_TASK_PREFIX = re.compile(r"^\[([ xX])\]\s+")


@dataclass(frozen=True)
class MarkdownUpdate:
    """One append-only commit and one replaceable live preview."""

    committed: str = ""
    preview: str = ""
    preview_changed: bool = True


class TerminalMarkdownRenderer:
    """Render a complete Markdown fragment as terminal-oriented text."""

    def __init__(self, *, columns: int = 80, color: bool = True) -> None:
        self.columns = max(8, columns)
        self.color = color
        self._parser = (
            MarkdownIt("commonmark", {"html": False})
            .enable("table")
            .enable("strikethrough")
        )

    def render(self, source: str) -> str:
        safe = _strip_controls(source)
        if not safe.strip():
            return ""
        lines = self._render_range(self._parser.parse(safe), 0, None)
        lines = _normalize_blank_lines(lines)
        if not lines:
            return ""
        return "\n".join(lines).rstrip() + "\n"

    def _render_range(
        self,
        tokens: Sequence[Token],
        start: int,
        end: int | None,
    ) -> list[str]:
        limit = len(tokens) if end is None else end
        lines: list[str] = []
        index = start
        while index < limit:
            token = tokens[index]
            kind = token.type

            if kind == "heading_open":
                close = _find_close(tokens, index, limit)
                inline = _first_inline(tokens, index + 1, close)
                level = int(token.tag[1:]) if token.tag.startswith("h") else 3
                marker = "◆" if level == 1 else ("▸" if level == 2 else "•")
                color = "36" if level == 1 else ("34" if level == 2 else "")
                body = self._render_inline(
                    inline.children if inline is not None else (),
                    base_styles=tuple(code for code in ("1", color) if code),
                )
                lines.append(f"{self._paint(marker, '1', color)} {body}".rstrip())
                lines.append("")
                index = close + 1
                continue

            if kind == "paragraph_open":
                close = _find_close(tokens, index, limit)
                inline = _first_inline(tokens, index + 1, close)
                body = self._render_inline(
                    inline.children if inline is not None else ()
                )
                lines.extend(body.splitlines() or [""])
                if not token.hidden:
                    lines.append("")
                index = close + 1
                continue

            if kind in {"bullet_list_open", "ordered_list_open"}:
                close = _find_close(tokens, index, limit)
                lines.extend(self._render_list(tokens, index, close))
                lines.append("")
                index = close + 1
                continue

            if kind == "blockquote_open":
                close = _find_close(tokens, index, limit)
                inner = _trim_blank_lines(
                    self._render_range(tokens, index + 1, close)
                )
                border = self._paint("│", "2")
                lines.extend(
                    f"{border} {line}" if line else border for line in inner
                )
                lines.append("")
                index = close + 1
                continue

            if kind in {"fence", "code_block"}:
                lines.extend(self._render_code(token.content, token.info))
                lines.append("")
                index += 1
                continue

            if kind == "table_open":
                close = _find_close(tokens, index, limit)
                lines.extend(self._render_table(tokens, index + 1, close))
                lines.append("")
                index = close + 1
                continue

            if kind == "hr":
                rule = "─" * max(3, min(self.columns - 1, 72))
                lines.extend((self._paint(rule, "2"), ""))
                index += 1
                continue

            if kind in {"html_block", "inline"}:
                if kind == "inline":
                    rendered = self._render_inline(token.children or ())
                else:
                    rendered = token.content
                lines.extend(rendered.rstrip("\n").splitlines())
                lines.append("")
                index += 1
                continue

            index += 1
        return lines

    def _render_list(
        self,
        tokens: Sequence[Token],
        open_index: int,
        close_index: int,
    ) -> list[str]:
        ordered = tokens[open_index].type == "ordered_list_open"
        value = int(tokens[open_index].attrGet("start") or 1)
        item_level = tokens[open_index].level + 1
        lines: list[str] = []
        index = open_index + 1
        while index < close_index:
            token = tokens[index]
            if token.type != "list_item_open" or token.level != item_level:
                index += 1
                continue
            item_close = _find_close(tokens, index, close_index)
            item_lines = _trim_blank_lines(
                self._render_range(tokens, index + 1, item_close)
            ) or [""]
            marker = f"{value}." if ordered else "•"
            task = _TASK_PREFIX.match(_SGR_ESCAPE.sub("", item_lines[0]))
            if task is not None:
                marker = "☑" if task.group(1).casefold() == "x" else "☐"
                item_lines[0] = _TASK_PREFIX.sub("", item_lines[0], count=1)
            styled_marker = self._paint(marker, "36")
            continuation = " " * (cell_width(marker) + 1)
            lines.append(f"{styled_marker} {item_lines[0]}".rstrip())
            lines.extend(
                f"{continuation}{line}" if line else "" for line in item_lines[1:]
            )
            value += 1
            index = item_close + 1
        return lines

    def _render_code(self, content: str, info: str) -> list[str]:
        language = info.strip().split(maxsplit=1)[0] if info.strip() else ""
        safe = _strip_controls(content).rstrip("\n")
        if self.color and safe:
            try:
                lexer = get_lexer_by_name(language) if language else TextLexer()
            except ClassNotFound:
                lexer = TextLexer()
            rendered = highlight(safe, lexer, TerminalFormatter()).rstrip("\n")
        else:
            rendered = safe
        label = language or "code"
        lines = [self._paint(f"  {label}", "2")]
        lines.extend(f"    {line}" for line in rendered.splitlines())
        if not safe:
            lines.append("    ")
        return lines

    def _render_table(
        self,
        tokens: Sequence[Token],
        start: int,
        end: int,
    ) -> list[str]:
        rows: list[list[str]] = []
        alignments: list[str] = []
        header_rows = 0
        in_header = False
        index = start
        while index < end:
            token = tokens[index]
            if token.type == "thead_open":
                in_header = True
            elif token.type == "thead_close":
                in_header = False
            elif token.type == "tr_open":
                row_close = _find_close(tokens, index, end)
                row: list[str] = []
                cell_index = index + 1
                while cell_index < row_close:
                    cell = tokens[cell_index]
                    if cell.type not in {"th_open", "td_open"}:
                        cell_index += 1
                        continue
                    cell_close = _find_close(tokens, cell_index, row_close)
                    inline = _first_inline(tokens, cell_index + 1, cell_close)
                    row.append(
                        self._inline_plain(
                            inline.children if inline is not None else ()
                        ).replace("\n", " ")
                    )
                    if not rows:
                        style = cell.attrGet("style") or ""
                        alignments.append(
                            "right" if "right" in style else (
                                "center" if "center" in style else "left"
                            )
                        )
                    cell_index = cell_close + 1
                rows.append(row)
                if in_header:
                    header_rows += 1
                index = row_close
            index += 1

        if not rows:
            return []
        columns = max(len(row) for row in rows)
        for row in rows:
            row.extend("" for _ in range(columns - len(row)))
        if len(alignments) < columns:
            alignments.extend("left" for _ in range(columns - len(alignments)))

        natural = [
            max(1, max(cell_width(row[column]) for row in rows))
            for column in range(columns)
        ]
        widths = _fit_table_widths(natural, self.columns)
        if widths is None:
            return self._render_table_as_records(rows, header_rows)

        def border(left: str, middle: str, right: str) -> str:
            raw = left + middle.join("─" * (width + 2) for width in widths) + right
            return self._paint(raw, "2")

        output = [border("┌", "┬", "┐")]
        for row_index, row in enumerate(rows):
            cells: list[str] = []
            for column, value in enumerate(row):
                visible = truncate_cells(value, widths[column])
                if alignments[column] == "right":
                    padded = visible.rjust(
                        len(visible) + max(0, widths[column] - cell_width(visible))
                    )
                elif alignments[column] == "center":
                    remaining = max(0, widths[column] - cell_width(visible))
                    padded = (" " * (remaining // 2)) + visible
                    padded = pad_cells(padded, widths[column])
                else:
                    padded = pad_cells(visible, widths[column])
                cells.append(
                    self._paint(padded, "1")
                    if row_index < header_rows
                    else padded
                )
            divider = self._paint("│", "2")
            output.append(f"{divider} " + f" {divider} ".join(cells) + f" {divider}")
            if row_index + 1 == header_rows and row_index < len(rows) - 1:
                output.append(border("├", "┼", "┤"))
        output.append(border("└", "┴", "┘"))
        return output

    def _render_table_as_records(
        self,
        rows: list[list[str]],
        header_rows: int,
    ) -> list[str]:
        headers = (
            rows[0]
            if header_rows
            else [f"Column {index + 1}" for index in range(len(rows[0]))]
        )
        data = rows[header_rows:] if header_rows else rows
        output: list[str] = []
        for row_index, row in enumerate(data):
            if row_index:
                output.append("")
            for header, value in zip(headers, row):
                label = self._paint(f"{header}:", "1", "36")
                output.append(f"{label} {value}".rstrip())
        return output

    def _render_inline(
        self,
        tokens: Sequence[Token],
        *,
        base_styles: tuple[str, ...] = (),
    ) -> str:
        output: list[str] = []
        styles: list[tuple[str, str]] = [("base", code) for code in base_styles]
        links: list[str] = []
        for token in tokens:
            kind = token.type
            if kind == "text":
                output.append(self._paint(token.content, *(code for _, code in styles)))
            elif kind == "code_inline":
                output.append(self._paint(token.content, "36"))
            elif kind in {"softbreak", "hardbreak"}:
                output.append("\n")
            elif kind in {"strong_open", "em_open", "s_open"}:
                code = {"strong_open": "1", "em_open": "3", "s_open": "9"}[kind]
                styles.append((kind.removesuffix("_open"), code))
            elif kind in {"strong_close", "em_close", "s_close"}:
                _pop_style(styles, kind.removesuffix("_close"))
            elif kind == "link_open":
                links.append(token.attrGet("href") or "")
                styles.append(("link", "4;34"))
            elif kind == "link_close":
                _pop_style(styles, "link")
                url = links.pop() if links else ""
                if url:
                    output.append(self._paint(f" ({url})", "2"))
            elif kind == "image":
                source = token.attrGet("src") or ""
                label = token.content or "image"
                output.append(self._paint(f"[image: {label}]", "36"))
                if source:
                    output.append(self._paint(f" ({source})", "2"))
            elif kind == "html_inline":
                output.append(self._paint(token.content, *(code for _, code in styles)))
        return "".join(output)

    def _inline_plain(self, tokens: Sequence[Token]) -> str:
        output: list[str] = []
        for token in tokens:
            if token.type in {"text", "code_inline", "html_inline"}:
                output.append(token.content)
            elif token.type in {"softbreak", "hardbreak"}:
                output.append("\n")
            elif token.type == "image":
                output.append(token.content or "image")
        return "".join(output)

    def _paint(self, text: str, *codes: str) -> str:
        active = [code for code in codes if code]
        if not self.color or not active or not text:
            return text
        return f"\033[{';'.join(active)}m{text}{_RESET}"


class MarkdownStreamPresenter:
    """Incrementally render stable blocks and replace the unfinished preview."""

    def __init__(self, *, columns: int = 80, color: bool = True) -> None:
        self.columns = max(8, columns)
        self.color = color
        self._pending = ""
        self._renderer = TerminalMarkdownRenderer(
            columns=self.columns,
            color=self.color,
        )
        self._preview = ""
        self._preview_source_size = 0
        self._preview_rendered_at = 0.0

    def feed(self, text: str, *, columns: int | None = None) -> MarkdownUpdate:
        resized = False
        if columns is not None:
            resized = max(8, columns) != self.columns
            self.columns = max(8, columns)
            self._renderer.columns = self.columns
        self._pending += _strip_controls(text)
        stable_end = _stable_prefix_end(self._pending)
        stable, self._pending = self._pending[:stable_end], self._pending[stable_end:]
        committed = self._renderer.render(stable) if stable else ""
        now = time.monotonic()
        should_render_preview = (
            bool(stable)
            or resized
            or not self._preview
            or "\n" in text
            or abs(len(self._pending) - self._preview_source_size) >= 16
            or now - self._preview_rendered_at >= 0.05
        )
        if should_render_preview:
            preview = (
                self._renderer.render(self._pending).rstrip("\n")
                if self._pending.strip()
                else ""
            )
            preview_changed = preview != self._preview
            self._preview = preview
            self._preview_source_size = len(self._pending)
            self._preview_rendered_at = now
        else:
            preview = self._preview
            preview_changed = False
        return MarkdownUpdate(
            committed=committed,
            preview=preview,
            preview_changed=preview_changed,
        )

    def flush(self, *, columns: int | None = None) -> MarkdownUpdate:
        if columns is not None:
            self.columns = max(8, columns)
            self._renderer.columns = self.columns
        committed = self._renderer.render(self._pending) if self._pending.strip() else ""
        preview_changed = bool(self._preview)
        self._pending = ""
        self._preview = ""
        self._preview_source_size = 0
        return MarkdownUpdate(
            committed=committed,
            preview="",
            preview_changed=preview_changed,
        )

    def reset(self) -> None:
        self._pending = ""
        self._preview = ""
        self._preview_source_size = 0


def _find_close(tokens: Sequence[Token], open_index: int, limit: int) -> int:
    opening = tokens[open_index]
    expected = opening.type.removesuffix("_open") + "_close"
    for index in range(open_index + 1, limit):
        token = tokens[index]
        if token.type == expected and token.level == opening.level:
            return index
    return min(open_index + 1, limit - 1)


def _first_inline(tokens: Sequence[Token], start: int, end: int) -> Token | None:
    return next((token for token in tokens[start:end] if token.type == "inline"), None)


def _pop_style(styles: list[tuple[str, str]], name: str) -> None:
    for index in range(len(styles) - 1, -1, -1):
        if styles[index][0] == name:
            del styles[index]
            return


def _normalize_blank_lines(lines: list[str]) -> list[str]:
    normalized: list[str] = []
    for line in lines:
        if not line and normalized and not normalized[-1]:
            continue
        normalized.append(line.rstrip())
    return _trim_blank_lines(normalized)


def _trim_blank_lines(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)
    while start < end and not lines[start]:
        start += 1
    while end > start and not lines[end - 1]:
        end -= 1
    return lines[start:end]


def _fit_table_widths(natural: list[int], columns: int) -> list[int] | None:
    available = columns - (3 * len(natural)) - 1
    # A one- or two-cell column is technically drawable but no longer readable;
    # use labeled records instead of presenting a table made only of ellipses.
    if available < 3 * len(natural):
        return None
    widths = natural.copy()
    while sum(widths) > available:
        largest = max(range(len(widths)), key=widths.__getitem__)
        if widths[largest] <= 1:
            return None
        widths[largest] -= 1
    return widths


def _stable_prefix_end(source: str) -> int:
    """Return the largest CommonMark block boundary safe to append once."""

    stable_end = 0
    offset = 0
    fence_character = ""
    fence_length = 0
    for line in source.splitlines(keepends=True):
        complete = line.endswith(("\n", "\r"))
        content = line.rstrip("\r\n")
        fence = _FENCE_OPEN.match(content)
        if fence_character:
            if (
                fence is not None
                and fence.group(1)[0] == fence_character
                and len(fence.group(1)) >= fence_length
                and not content[fence.end() :].strip()
            ):
                fence_character = ""
                fence_length = 0
                if complete:
                    stable_end = offset + len(line)
        elif fence is not None:
            marker = fence.group(1)
            fence_character = marker[0]
            fence_length = len(marker)
        elif complete and (
            not content.strip()
            or _ATX_HEADING.match(content)
            or _HORIZONTAL_RULE.match(content)
        ):
            stable_end = offset + len(line)
        offset += len(line)
    return stable_end


def _strip_controls(text: str) -> str:
    text = _CONTROL_ESCAPE.sub("", text)
    return "".join(
        character
        for character in text
        if character in {"\n", "\r", "\t"}
        or not unicodedata.category(character).startswith("C")
    )


__all__ = [
    "MarkdownStreamPresenter",
    "MarkdownUpdate",
    "TerminalMarkdownRenderer",
]
