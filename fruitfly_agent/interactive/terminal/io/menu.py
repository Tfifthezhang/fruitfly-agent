"""Generic option-menu input and rendering for terminal frontends."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
import select
import shutil
import textwrap
from typing import Any, Protocol, TextIO

from fruitfly_agent.interactive.terminal.io.input import LineEditor
from fruitfly_agent.interactive.terminal.io.text import (
    colors_enabled, is_tty, supports_ansi, input_styles, safe_terminal_text, truncate_cells, cell_width,
)


class MenuAction(str, Enum):
    IGNORE = "ignore"
    UP = "up"
    DOWN = "down"
    ACTIVATE = "activate"
    TOGGLE = "toggle"
    PAGE_UP = "page_up"
    PAGE_DOWN = "page_down"
    SECTION_NEXT = "section_next"
    SECTION_PREVIOUS = "section_previous"
    BACK = "back"
    QUIT = "quit"


@dataclass(frozen=True)
class MenuEvent:
    action: MenuAction
    index: int | None = None


class MenuInput(Protocol):
    def read_event(self) -> MenuEvent: ...


@dataclass(frozen=True)
class MenuHelp:
    """Plain explanation supplied by a menu owner, independent of layout."""

    title: str
    text: str


@dataclass(frozen=True)
class MenuRow:
    label: str
    detail: str = ""
    marker: str = ""
    depth: int = 0
    section: str = ""
    state: str = ""
    changed: bool = False
    references: tuple[tuple[str, str], ...] = ()
    help: MenuHelp | None = None


class RawTerminalMenuInput:
    """Read one POSIX terminal key while restoring terminal state every time."""

    def __init__(self, input_stream: TextIO) -> None:
        self.input = input_stream

    def read_event(self) -> MenuEvent:
        return self._read_event(None)

    def poll_event(self, timeout: float = .1) -> MenuEvent:
        """Bounded read using this same input owner while asynchronous work runs."""
        return self._read_event(timeout)

    def _read_event(self, timeout: float | None) -> MenuEvent:
        import termios
        import tty

        descriptor = self.input.fileno()
        previous = termios.tcgetattr(descriptor)
        blocking = os.get_blocking(descriptor)
        try:
            # Preserve keys queued between polls instead of flushing them.
            tty.setraw(descriptor, when=termios.TCSANOW)
            if timeout is not None:
                os.set_blocking(descriptor, False)
            if timeout is not None and not select.select([descriptor], [], [], timeout)[0]:
                return MenuEvent(MenuAction.IGNORE)
            try:
                first = os.read(descriptor, 1)
            except BlockingIOError:
                return MenuEvent(MenuAction.IGNORE)
            if not first or first == b"\x04":
                return MenuEvent(MenuAction.QUIT)
            if first == b"\x03":
                raise KeyboardInterrupt
            sequence = first
            if first == b"\x1b":
                while len(sequence) < 8 and select.select(
                    [descriptor], [], [], 0.02
                )[0]:
                    try:
                        sequence += os.read(descriptor, 1)
                    except BlockingIOError:
                        break
            return self.decode(sequence)
        finally:
            try:
                os.set_blocking(descriptor, blocking)
            finally:
                termios.tcsetattr(descriptor, termios.TCSANOW if timeout is not None else termios.TCSADRAIN, previous)

    @staticmethod
    def decode(sequence: bytes) -> MenuEvent:
        if sequence in {b'n', b'N'}:
            return MenuEvent(MenuAction.SECTION_NEXT)
        if sequence in {b'p', b'P'}:
            return MenuEvent(MenuAction.SECTION_PREVIOUS)
        if sequence in {b"\x1b[A", b"k", b"K"}:
            return MenuEvent(MenuAction.UP)
        if sequence in {b"\x1b[B", b"j", b"J", b"\t"}:
            return MenuEvent(MenuAction.DOWN)
        if sequence in {b"\r", b"\n", b"\x1b[C"}:
            return MenuEvent(MenuAction.ACTIVATE)
        if sequence == b"\x1b[5~":
            return MenuEvent(MenuAction.PAGE_UP)
        if sequence == b"\x1b[6~":
            return MenuEvent(MenuAction.PAGE_DOWN)
        if sequence == b" ":
            return MenuEvent(MenuAction.TOGGLE)
        if sequence in {b"\x1b", b"\x1b[D", b"h", b"H"}:
            return MenuEvent(MenuAction.BACK)
        if sequence in {b"q", b"Q"}:
            return MenuEvent(MenuAction.QUIT)
        return MenuEvent(MenuAction.IGNORE)


class LineMenuInput:
    """Numbered fallback for redirected streams and non-ANSI terminals."""

    def __init__(self, line_editor: LineEditor) -> None:
        self.line_editor = line_editor

    def read_event(self) -> MenuEvent:
        value = self.line_editor.read_line()
        if value is None:
            return MenuEvent(MenuAction.QUIT)
        text = value.strip().casefold()
        if not text:
            return MenuEvent(MenuAction.ACTIVATE)
        if text.isdecimal():
            return MenuEvent(MenuAction.ACTIVATE, int(text) - 1)
        actions = {
            "up": MenuAction.UP,
            "k": MenuAction.UP,
            "down": MenuAction.DOWN,
            "j": MenuAction.DOWN,
            "space": MenuAction.TOGGLE,
            "pageup": MenuAction.PAGE_UP,
            "pagedown": MenuAction.PAGE_DOWN,
            "next": MenuAction.SECTION_NEXT,
            "previous": MenuAction.SECTION_PREVIOUS,
            "toggle": MenuAction.TOGGLE,
            "back": MenuAction.BACK,
            "b": MenuAction.BACK,
            "q": MenuAction.QUIT,
            "quit": MenuAction.QUIT,
            "/exit": MenuAction.QUIT,
        }
        return MenuEvent(actions.get(text, MenuAction.IGNORE))


class TerminalMenuRenderer:
    """Render generic rows; it has no knowledge of configuration semantics."""

    def __init__(self, output_stream: TextIO) -> None:
        self.output = output_stream
        self.ansi = supports_ansi(output_stream)
        self.color = colors_enabled(output_stream)
        self.numbered: bool | None = None
        self._rendered = False
        self._last_frame: dict[str, Any] = {}
        self.reference_page = 0

    def begin_input(self, prompt: str, *, selected: int | None = None) -> None:
        """Keep the current menu and focused field visible while borrowing its reader."""
        frame = self._last_frame or dict(title='Input', subtitle='', rows=(), selected=0)
        self.render(**{**frame, 'selected': frame['selected'] if selected is None else selected, 'notice': '', 'field': prompt,
            'instructions': 'Enter submit · Esc or /cancel keep current'})

    def render(
        self,
        *,
        title: str,
        subtitle: str,
        rows: tuple[MenuRow, ...],
        selected: int,
        notice: str = "",
        instructions: str = "↑↓ move · Enter select · Space toggle · Esc back · q quit",
        field: str = '',
        reference_page: int = 0,
        help_panel: bool = False,
    ) -> None:
        if not field:
            self._last_frame = dict(title=title, subtitle=subtitle, rows=rows, selected=selected,
                notice=notice, instructions=instructions, reference_page=reference_page, help_panel=help_panel)
        try:
            size = os.get_terminal_size(self.output.fileno())
        except (AttributeError, OSError, ValueError):
            size = shutil.get_terminal_size(fallback=(80, 24))
        columns, height = max(8, size.columns), max(10, size.lines)
        selected = min(max(0, selected), len(rows) - 1) if rows else 0
        parts: list[str] = []
        write = parts.append
        numbered = not self.ansi if self.numbered is None else self.numbered
        if self.ansi:
            write("\x1b[2J\x1b[H")
        elif self._rendered:
            write("\n")
        self._rendered = True
        def styled(value: str, style: str) -> str:
            return f'\x1b[{style}m{value}\x1b[0m' if self.color else value

        def plain(value: str) -> str:
            return safe_terminal_text(value).replace('\n', ' ').replace('\t', ' ')

        help_slots = (4 if height >= 18 else 3) if help_panel else 0
        compact = help_panel and self.ansi and height < 18
        field_lines = safe_terminal_text(field).splitlines()
        if self.ansi:
            field_limit = max(1, height - help_slots - 9) if help_panel else max(4, height // 2)
            field_lines = [truncate_cells(line, columns - 1) for line in field_lines[:field_limit]]

        subtitle_lines = [part for line in safe_terminal_text(subtitle).splitlines()
            for part in (textwrap.wrap(line, max(16, columns - 2)) or [''])]
        if self.ansi:
            subtitle_limit = (0 if height < 18 or field else 2) if help_panel else (1 if field else max(2, height - 12))
            subtitle_lines = subtitle_lines[:subtitle_limit]
        write(styled(truncate_cells(plain(title), columns - 1) if self.ansi else plain(title), '1') + ('\n' if compact else '\n\n'))
        if subtitle_lines:
            write(styled('\n'.join(subtitle_lines), '2') + '\n')
        if not compact:
            write('\n')
        start, end = 0, len(rows)
        self.reference_page = 0
        def reference_lines(row: MenuRow) -> list[str]:
            width = max(8, columns - 5 - 2 * row.depth)
            lines = [part for label, path in row.references
                    for part in textwrap.wrap(plain(label) + ': ' + plain(path), width,
                                              break_on_hyphens=False)]
            limit = max(1, height - len(subtitle_lines) - len(field_lines) - bool(field) - 13 - help_slots)
            if self.ansi and not numbered and len(lines) > limit:
                pages = (len(lines) + limit - 1) // limit
                page = min(max(0, reference_page), pages - 1) if row is rows[selected] else 0
                if row is rows[selected]:
                    self.reference_page = page
                return lines[page * limit:(page + 1) * limit] + [f'Details {page + 1}/{pages} · PageUp/PageDown']
            return lines
        if self.ansi and not numbered and rows:
            # Titles are decorations on actionable rows, so they never consume
            # selection indices. Repeat the current section after scrolling.
            if help_panel:
                budget = max(2, height - (1 if compact else 3) - len(subtitle_lines) - help_slots
                    - (len(field_lines) + 1 if field_lines else 0) - (2 if notice else 0)
                    - (2 if compact else 4))
            else:
                budget = max(2, height - len(subtitle_lines) - len(field_lines) - bool(field) - 10)
            def cost(first: int, last: int) -> int:
                return sum(1 + bool(r.detail) + len(reference_lines(r)) + bool(r.section and
                    (i == first or r.section != rows[i - 1].section))
                    for i, r in enumerate(rows[first:last], first))
            selected = min(max(0, selected), len(rows) - 1)
            while start < selected and cost(start, selected + 1) > budget:
                start += 1
            end = selected + 1
            while end < len(rows) and cost(start, end + 1) <= budget:
                end += 1
            if start and not compact:
                write(styled('  ↑ More above\n', '2'))
        previous_section = ''
        for index in range(start, end):
            row = rows[index]
            if row.section and row.section != previous_section:
                write(styled('  ' + plain(row.section), '1;34') + '\n')
            previous_section = row.section
            cursor = ('>' if numbered else '❯') if index == selected else ' '
            indent = '  ' * max(0, row.depth)
            number = f'{index + 1}. ' if numbered else ''
            marker = row.marker
            state = row.state or ('selected' if marker in {'✓', '[✓]', '●'} else '')
            label = plain(row.label)
            suffix = ' · Modified' if row.changed else ''
            prefix = f'{cursor} {number}{indent}'
            if self.ansi:
                label = truncate_cells(label, max(1, columns - cell_width(prefix + marker + suffix) - 2))
            if self.color:
                fill = input_styles(self.output)[0] if index == selected else ''
                focus = '\x1b[1;36m' if index == selected else '\x1b[1m'
                marker_style = '32' if state in {'selected', 'enabled'} else '33' if state == 'unavailable' else '2'
                marker_text = f'\x1b[{marker_style}m{marker}\x1b[0m{fill}{focus} ' if marker else ''
                if state == 'unavailable' and index != selected:
                    focus = '\x1b[2m'
                line = f'{fill}{focus}{prefix}{marker_text}{label}'
                if suffix:
                    line += '\x1b[33m' + suffix
                line += '\x1b[0m'
            else:
                line = prefix + (marker + ' ' if marker else '') + label + suffix
            write(line + '\n')
            if row.detail:
                detail = plain(row.detail)
                if self.ansi:
                    detail = truncate_cells(detail, max(1, columns - len(indent) - 5))
                write(styled('     ' + indent + detail, '2') + '\n')
            for reference in reference_lines(row):
                write(styled('     ' + indent + reference, '2') + '\n')
        if self.ansi and end < len(rows) and not compact:
            write(styled('  ↓ More below\n', '2'))
        if help_panel:
            explanation = rows[selected].help if rows else None
            # Reserve a stable footer even on Back or rows with no explanation.
            footer = [styled('─' * (columns - 1), '2')]
            footer.append(styled(truncate_cells(plain(explanation.title), columns - 1), '1') if explanation else '')
            body = _wrap_help(plain(explanation.text), columns - 1) if explanation else []
            if self.ansi and not numbered:
                body = body[:help_slots - 2]
                if explanation and len(_wrap_help(plain(explanation.text), columns - 1)) > len(body):
                    body[-1] = truncate_cells(body[-1], columns - 3).rstrip('…') + ' …'
            footer.extend(styled(line, '2') for line in body)
            footer.extend([''] * max(0, help_slots - len(footer)))
            if self.ansi and not numbered:
                used = ''.join(parts).count('\n')
                tail = (2 if notice else 0) + (len(field_lines) + 1 if field_lines else 0) + 2
                write('\n' * max(0, height - help_slots - tail - used))
            write('\n'.join(footer) + '\n')
        if notice:
            error = notice.startswith(('Invalid', 'Cannot', 'Could not', 'Error', 'Experiment preview unavailable'))
            visible_notice = truncate_cells(plain(notice), columns - 1) if self.ansi else safe_terminal_text(notice)
            write('\n' + styled(visible_notice, '31' if error else '33') + '\n')
        if field_lines:
            write('\n' + styled(field_lines[0], '1;36') + '\n')
            if len(field_lines) > 1:
                write('\n'.join(field_lines[1:]) + '\n')
        ending = '' if help_panel and self.ansi and not numbered else '\n'
        write('\n' + styled(truncate_cells(instructions, columns - 1) if self.ansi else instructions, '2') + ending)
        self.output.write(''.join(parts))
        self.output.flush()


def _wrap_help(text: str, width: int) -> list[str]:
    """Wrap words and long tokens using terminal cells rather than code points."""
    lines: list[str] = []
    line = ''
    for word in text.split():
        candidate = line + (' ' if line else '') + word
        if cell_width(candidate) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
        line = ''
        for char in word:
            if line and cell_width(line + char) > width:
                lines.append(line)
                line = ''
            line += char
    if line:
        lines.append(line)
    return lines


def create_menu_input(
    input_stream: TextIO,
    output_stream: TextIO,
    line_editor: LineEditor,
) -> MenuInput:
    """Use immediate keys on a real ANSI TTY and numbered input elsewhere."""

    if (
        is_tty(input_stream)
        and is_tty(output_stream)
        and supports_ansi(output_stream)
        and os.name == "posix"
    ):
        return RawTerminalMenuInput(input_stream)
    return LineMenuInput(line_editor)


__all__ = [
    "navigate_menu",
    "LineMenuInput",
    "MenuAction",
    "MenuEvent",
    "MenuInput",
    "MenuRow",
    "MenuHelp",
    "RawTerminalMenuInput",
    "TerminalMenuRenderer",
    "create_menu_input",
]


def navigate_menu(event: MenuEvent, selected: int, size: int) -> tuple[int, bool]:
    if event.index is not None:
        return (event.index, False) if 0 <= event.index < size else (selected, True)
    if event.action == MenuAction.UP:
        return (selected - 1) % size, True
    if event.action == MenuAction.DOWN:
        return (selected + 1) % size, True
    return selected, False

