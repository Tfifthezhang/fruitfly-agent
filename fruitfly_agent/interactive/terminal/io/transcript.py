"""Display-only records and viewport anchors, independent of event semantics."""

from collections.abc import Callable
from dataclasses import dataclass, field
import re

Formatter = Callable[[str, int], str]
Wrapper = Callable[[str, int], list[str]]
_STYLES = re.compile(r"\x1b\[[0-9;]*m")


def _length(line: str) -> int:
    return len("".join(_STYLES.sub("", line).split()))


@dataclass
class DisplayRecord:
    source: str
    formatter: Formatter | None = None
    cache: dict[int, list[str]] = field(default_factory=dict)


class DisplayTranscript:
    """Retain presentation sources; callers supply formatting and line wrapping.

    A scrolled viewport anchors to a record and a visible-character offset.
    Appending output therefore does not move the reader back to the bottom.
    """

    def __init__(self, wrap: Wrapper) -> None:
        self.wrap = wrap
        self.records: list[DisplayRecord] = []
        self.pending: DisplayRecord | None = None
        self.anchor: tuple[int, int] | None = None
        self.layout_columns: int | None = None
        self.layout_lines: list[tuple[int, int, str]] = []

    def append(self, text: str) -> None:
        if not text:
            return
        self.layout_columns = None
        self.pending = None
        if self.records and self.records[-1].formatter is None:
            record = self.records[-1]
            record.source += text
            record.cache.clear()
        else:
            self.records.append(DisplayRecord(text))

    def update(self, source: str, formatter: Formatter, *, complete: bool) -> None:
        self.layout_columns = None
        if self.pending is None:
            self.pending = DisplayRecord(source, formatter)
            self.records.append(self.pending)
        else:
            self.pending.source = source
            self.pending.formatter = formatter
            self.pending.cache.clear()
        if complete:
            self.pending = None

    def layout(self, columns: int) -> list[tuple[int, int, str]]:
        if self.layout_columns == columns:
            return self.layout_lines
        output: list[tuple[int, int, str]] = []
        for index, record in enumerate(self.records):
            if columns not in record.cache:
                text = record.formatter(record.source, columns) if record.formatter else record.source
                # Cache only the current width so repeated resizes stay bounded.
                record.cache = {columns: self.wrap(text, columns)}
            offset = 0
            for line in record.cache[columns]:
                output.append((index, offset, line))
                offset += _length(line)
        self.layout_columns, self.layout_lines = columns, output
        return output

    def start(self, lines: list[tuple[int, int, str]], height: int) -> int:
        bottom = max(0, len(lines) - height)
        if self.anchor is None:
            return bottom
        record, offset = self.anchor
        start = 0
        for index, (identity, position, _) in enumerate(lines):
            if identity > record or (identity == record and position > offset):
                break
            start = index
        return min(start, bottom)

    def view(self, columns: int, height: int) -> list[str]:
        if height <= 0:
            return []
        lines = self.layout(columns)
        start = self.start(lines, height)
        return [line for _, _, line in lines[start:start + height]]

    def scroll(self, amount: int | None, columns: int, height: int) -> None:
        if amount is None:
            self.anchor = None
            return
        lines = self.layout(columns)
        bottom = max(0, len(lines) - height)
        start = min(bottom, max(0, self.start(lines, height) + amount))
        self.anchor = lines[start][:2] if lines and start < bottom else None


__all__ = ["DisplayTranscript", "Formatter"]
