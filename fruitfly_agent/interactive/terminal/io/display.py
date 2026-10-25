"""Transcript viewport and editable surface, independent of input decoding."""
from __future__ import annotations
import os
import re
import threading
from typing import Callable, Sequence, TextIO
from .transcript import DisplayTranscript, Formatter
from .controls import ViewAction, view_action
from .screen import TerminalScreen
from .completion import CompletionView
from .text import cell_width, colors_enabled, input_styles, safe_terminal_text, terminal_columns, truncate_cells

_ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|[78])")
_SGR_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
_CLEAR_LINE = "\x1b[2K"
_RESET_STYLE = "\x1b[0m"

def prompt_frame_lines(columns: int, label: str = "prompt") -> tuple[str, str]:
    """Return borders that avoid the terminal's auto-wrap column."""

    width = max(4, columns - 1)
    label = "─ " + label + " "
    label_width = cell_width(label)
    if width >= label_width + 2:
        top = "╭" + label + ("─" * (width - label_width - 2)) + "╮"
    else:
        top = "╭" + ("─" * (width - 2)) + "╮"
    return top, "╰" + ("─" * (width - 2)) + "╯"


class InlineTerminalDisplay:
    """Serialize transcript and input drawing; optionally own a reflowable screen."""

    def __init__(
        self,
        output: TextIO,
        *,
        rows: int | None = None,
        columns: int | None = None,
        fullscreen: bool = False,
    ) -> None:
        self.output = output
        self.fullscreen = fullscreen
        self.screen = TerminalScreen(output, fullscreen=fullscreen)
        self._mouse_requested = False
        self._copy_lines: tuple[str, ...] | None = None
        self._copy_start = 0
        self.transcript = DisplayTranscript(lambda text, width: _visual_lines(_sanitize_output(text), width))
        self._history_height = 1
        self._fixed_rows = rows
        self._fixed_columns = columns
        self._rows = 0
        self._columns = 0
        self._active = False
        self._pending_output = ""
        self._assistant_preview = ""
        self._activity = ""
        self._input = ""
        self._cursor = 0
        self._choices: tuple[str, ...] = ()
        self._completion_view = CompletionView()
        self._selected_choice = 0
        self._live_rows = 0
        self._cursor_live_row = 0
        self._rendered_rows: tuple[str, ...] = ()
        self._cursor_column = 0
        self._lock = threading.RLock()

    @property
    def active(self) -> bool:
        return self._active

    @property
    def encoding(self) -> str | None:
        return getattr(self.output, "encoding", None)

    @property
    def formatted_output(self) -> Callable[..., None] | None:
        """Advertise source-backed output only when this sink can repaint it."""
        return self.update_formatted if self.fullscreen else None

    def isatty(self) -> bool:
        return True

    def fileno(self) -> int:
        return self.output.fileno()

    def write(self, text: str) -> int:
        with self._lock:
            if self.fullscreen:
                self.transcript.append(_sanitize_output(text))
                if self._active:
                    self._measure_locked()
                    self._render_live_locked()
            elif not self._active:
                self.output.write(text)
            else:
                visible = _sanitize_output(text)
                self._measure_locked()
                self._erase_live_locked()
                self._pending_output += visible
                self._commit_ready_output_locked()
                self._render_live_locked()
            self.output.flush()
        return len(text)

    def update_formatted(self, source: str, formatter: Formatter, *, complete: bool = False) -> None:
        """Update a source-backed display record using caller-owned formatting."""
        with self._lock:
            self.transcript.update(source, formatter, complete=complete)
            if self._active:
                self._measure_locked()
                self._render_live_locked()
                self.output.flush()

    @property
    def copying(self) -> bool:
        return self._copy_lines is not None

    def create_field_display(self) -> InlineTerminalDisplay:
        return InlineTerminalDisplay(self.output)

    def resume_live(self) -> None:
        with self._lock:
            if not self.copying:
                return
            self._copy_lines = None
            self.transcript.scroll(None, self._columns - 1, self._history_height)
            self.screen.set_mouse(self._mouse_requested)
            if self._active:
                self._render_live_locked()
                self.output.flush()

    def scroll_history(self, sequence: bytes) -> bool:
        """Compatibility entry; input owners should dispatch typed view actions."""
        action = view_action(sequence)
        return self.handle_action(action) if action is not None else False

    def handle_action(self, action: ViewAction) -> bool:
        if not self.fullscreen or not self._active:
            return False
        with self._lock:
            self._measure_locked()
            if action == ViewAction.EXIT_COPY:
                if not self.copying:
                    return False
                self.resume_live()
            elif action == ViewAction.TOGGLE_COPY:
                if self._choices:
                    return True
                if self.copying:
                    self.resume_live()
                else:
                    self._completion_view = CompletionView()
                    layout = self.transcript.layout(self._columns - 1)
                    self._copy_lines = tuple(line for _, _, line in layout)
                    self._copy_start = self.transcript.start(layout, self._history_height)
                    self.screen.set_mouse(False)
                    self._render_copy_locked()
            elif action == ViewAction.TOGGLE_MOUSE:
                if not self.copying:
                    self._mouse_requested = not self._mouse_requested
                    self.screen.set_mouse(self._mouse_requested)
                    self._render_live_locked()
            else:
                if action in {ViewAction.WHEEL_UP, ViewAction.WHEEL_DOWN} and not self.screen.mouse:
                    return True
                amount = {
                    ViewAction.PAGE_UP: -max(1, self._history_height - 1),
                    ViewAction.PAGE_DOWN: max(1, self._history_height - 1),
                    ViewAction.WHEEL_UP: -3, ViewAction.WHEEL_DOWN: 3,
                    ViewAction.LATEST: None,
                }[action]
                if self.copying:
                    assert self._copy_lines is not None
                    bottom = max(0, len(self._copy_lines) - (self._rows - 1))
                    self._copy_start = bottom if amount is None else min(bottom, max(0, self._copy_start + amount))
                    self._render_copy_locked()
                else:
                    self.transcript.scroll(amount, self._columns - 1, self._history_height)
                    self._render_live_locked()
            self.output.flush()
        return True

    def _render_copy_locked(self) -> None:
        assert self._copy_lines is not None
        height = self._rows - 1
        start = min(self._copy_start, max(0, len(self._copy_lines) - height))
        rows = list(self._copy_lines[start:start + height])
        rows += [''] * (height - len(rows))
        rows.append(truncate_cells('Copy: drag to select · PgUp/PgDn · Esc/F2 live', self._columns - 1))
        reset = _RESET_STYLE if colors_enabled(self.output) else ''
        self.output.write('\x1b[H' + '\r\n'.join(reset + _CLEAR_LINE + row for row in rows))
        self._rendered_rows = tuple(rows)

    def flush(self) -> None:
        with self._lock:
            self.output.flush()

    def update_assistant(self, committed: str, preview: str) -> None:
        """Atomically append stable answer blocks and replace the live tail."""

        with self._lock:
            committed = _sanitize_output(committed)
            preview = _sanitize_output(preview)
            if not self._active:
                if committed:
                    self.output.write(committed)
                self._assistant_preview = preview
            else:
                self._measure_locked()
                self._erase_live_locked()
                if committed:
                    self._pending_output += committed
                    self._commit_ready_output_locked()
                self._assistant_preview = preview
                self._render_live_locked()
            self.output.flush()

    def activate(self) -> None:
        with self._lock:
            if self._active:
                return
            self._measure_locked()
            self._active = True
            self.screen.activate()
            if self.fullscreen and self._mouse_requested:
                self.screen.set_mouse(True)
            # Newlines inside a bracketed paste belong to one editable prompt;
            # only an Enter outside the delimiters submits it.
            self._render_live_locked()
            self.output.flush()

    def suspend(self) -> None:
        """Remove the editable frame and leave a normal terminal viewport."""

        with self._lock:
            if not self._active:
                return
            if self.fullscreen:
                self._copy_lines = None
                self._completion_view = CompletionView()
                self.screen.suspend()
                self.output.flush()
                self._active = False
                self._live_rows = 0
                return
            self._measure_locked()
            self._erase_live_locked()
            if self._pending_output:
                self.output.write(self._pending_output)
                self.output.write("\r\n")
                self._pending_output = ""
            if self._assistant_preview:
                self.output.write(self._assistant_preview)
                self.output.write("\r\n")
                self._assistant_preview = ""
            self.screen.suspend()
            self.output.flush()
            self._active = False

    def set_input(self, text: str, cursor: int) -> None:
        with self._lock:
            cursor = min(max(cursor, 0), len(text))
            if (text, cursor) == (self._input, self._cursor):
                return
            self._input = text
            self._cursor = cursor
            if self._active:
                self._measure_locked()
                self._erase_live_locked()
                self._commit_ready_output_locked()
                self._render_live_locked()
                self.output.flush()

    def set_activity(self, text: str) -> None:
        """Replace the transient run status without committing it to history."""

        with self._lock:
            sanitized = _sanitize_output(text).replace("\r", " ").replace("\n", " ")
            self._activity = sanitized.strip()
            if self._active:
                self._measure_locked()
                self._erase_live_locked()
                self._commit_ready_output_locked()
                self._render_live_locked()
                self.output.flush()

    def set_choices(self, labels: Sequence[str] = (), selected: int = 0) -> None:
        """Replace the input frame with transient, keyboard-selectable choices."""
        with self._lock:
            self._completion_view = CompletionView()
            if labels:
                self.resume_live()
            self._choices = tuple(
                safe_terminal_text(label).replace("\n", " ").replace("\t", " ")
                for label in labels
            )
            self._selected_choice = min(max(selected, 0), max(0, len(self._choices) - 1))
            self._input, self._cursor = "", 0
            if self._active:
                self._measure_locked()
                self._erase_live_locked()
                self._render_live_locked()
                self.output.flush()

    def set_completions(self, view: CompletionView) -> None:
        """Render a read-only candidate view without replacing the editable draft."""
        if not self.fullscreen:
            return
        with self._lock:
            if self._choices or self.copying:
                view = CompletionView()
            if view == self._completion_view:
                return
            self._completion_view = view
            if self._active:
                self._measure_locked()
                self._render_live_locked()
                self.output.flush()

    def refresh(self) -> None:
        """Redraw on a size change without changing the input buffer or transcript."""
        with self._lock:
            if not self._active:
                return
            previous = self._rows, self._columns
            self._measure_locked()
            if previous == (self._rows, self._columns):
                return
            self._erase_live_locked()
            self._commit_ready_output_locked()
            self._render_live_locked()
            self.output.flush()

    def _measure_locked(self) -> None:
        if self._fixed_rows is not None and self._fixed_columns is not None:
            rows, columns = self._fixed_rows, self._fixed_columns
        else:
            try:
                size = os.get_terminal_size(self.output.fileno())
                rows, columns = size.lines, size.columns
            except (AttributeError, OSError, ValueError):
                rows, columns = 24, terminal_columns(self.output)
        new_rows, new_columns = max(6, rows), max(8, columns)
        if not self.fullscreen and self._live_rows and self._columns != new_columns:
            # Each rendered row ends in an explicit newline. A narrower terminal
            # can wrap it into several physical rows before we get to repaint.
            lengths = [max(1, len(_visual_lines(row, new_columns))) for row in self._rendered_rows]
            cursor_row = sum(lengths[:self._cursor_live_row]) + min(
                self._cursor_column // new_columns, lengths[self._cursor_live_row] - 1)
            total = sum(lengths)
            clipped = max(0, total - new_rows)
            self._live_rows = min(total, new_rows)
            self._cursor_live_row = max(0, cursor_row - clipped)
        if self.copying and (new_rows, new_columns) != (self._rows, self._columns):
            self._copy_lines = None
            self.screen.set_mouse(self._mouse_requested)
        self._rows, self._columns = new_rows, new_columns

    def _commit_ready_output_locked(self) -> None:
        """Commit every complete logical or visual line to terminal history."""

        if self.fullscreen or not self._pending_output:
            return
        width = max(4, self._columns - 1)
        lines = _visual_lines(self._pending_output, width)
        # SGR resets are zero-width and may legally follow a newline.  Looking
        # at the raw suffix would keep completed colored records in the live
        # tail and concatenate the next tool/assistant record onto them.
        ends_line = _SGR_ESCAPE.sub("", self._pending_output).endswith(
            ("\n", "\r")
        )
        commit_count = len(lines) if ends_line else max(0, len(lines) - 1)
        for line in lines[:commit_count]:
            self.output.write(f"{line}\r\n")
        self._pending_output = "" if ends_line else lines[-1]

    def _erase_live_locked(self) -> None:
        """Erase only rows owned by the live surface, never committed history."""

        if self.fullscreen or not self._live_rows:
            return
        self.output.write("\r")
        if self._cursor_live_row:
            self.output.write(f"\x1b[{self._cursor_live_row}A")
        for row in range(self._live_rows):
            self.output.write(_CLEAR_LINE)
            if row < self._live_rows - 1:
                self.output.write("\x1b[1B\r")
        if self._live_rows > 1:
            self.output.write(f"\x1b[{self._live_rows - 1}A\r")
        self._live_rows = 0
        self._cursor_live_row = 0
        self._rendered_rows = ()

    def _render_live_locked(self) -> None:
        if self.copying:
            return
        input_width = max(1, self._columns - cell_width("❯ ") - 2)
        all_input_lines, cursor_line, cursor_cells = _input_visual_lines(
            self._input,
            self._cursor,
            input_width,
        )
        if self._choices:
            all_input_lines = [truncate_cells(label, input_width) for label in self._choices]
            cursor_line, cursor_cells = self._selected_choice, 0
        choice_footer = int(bool(self._choices))
        view_footer = int(self.fullscreen and not self._choices)
        input_padding = 0 if self._choices or (self._completion_view.items and self._rows < 12) else 2
        pending_lines = (
            _visual_lines(self._pending_output, max(4, self._columns - 1))
            if self._pending_output
            else []
        )
        all_preview_lines = (
            _visual_lines(
                self._assistant_preview,
                max(4, self._columns - 1),
            )
            if self._assistant_preview
            else []
        )
        activity_lines = (
            [truncate_cells(self._activity, max(4, self._columns - 1))]
            if self._activity
            else []
        )
        completion_limit = min(5, max(1, self._rows - len(activity_lines) - input_padding - view_footer - 2))
        completion_lines = _completion_lines(self._completion_view, self._columns - 1, completion_limit,
                                             colors_enabled(self.output))
        preview_budget = max(
            0,
            self._rows - len(pending_lines) - len(activity_lines) - len(completion_lines) - 2 - choice_footer - input_padding - view_footer,
        )
        preview_lines = (
            all_preview_lines[-preview_budget:] if preview_budget else []
        )
        if preview_lines and len(preview_lines) < len(all_preview_lines):
            preview_lines[0] = f"… {preview_lines[0]}"
        max_input_lines = max(
            1,
            self._rows
            - len(pending_lines)
            - len(preview_lines)
            - len(activity_lines)
            - len(completion_lines)
            - 1
            - choice_footer
            - input_padding
            - view_footer,
        )
        if self.fullscreen:
            max_input_lines = min(max_input_lines, max(1, self._rows // 3))
        input_start = max(0, cursor_line - max_input_lines + 1)
        input_lines = all_input_lines[input_start : input_start + max_input_lines]
        cursor_line -= input_start

        rows: list[str] = [
            *pending_lines,
            *preview_lines,
            *activity_lines,
            *completion_lines,
        ]
        input_base = len(rows)
        fill, accent = input_styles(self.output)

        def input_row_text(prefix: str, text: str) -> str:
            if not fill:
                return prefix + text
            padding = " " * max(0, self._columns - 1 - cell_width(prefix + text))
            return f"{fill}{accent}{prefix}\x1b[22m{fill}{text}{padding}{_RESET_STYLE}"

        if input_padding:
            rows.append(input_row_text("", ""))
        for index, input_text in enumerate(input_lines, start=input_start):
            if self._choices:
                selected = index == self._selected_choice
                row = f"{'❯' if selected else ' '} {input_text}"
                if selected and colors_enabled(self.output):
                    row = f"\x1b[1;36m{row}{_RESET_STYLE}"
                rows.append(row)
            else:
                prefix = "❯ " if index == 0 else "│ "
                rows.append(input_row_text(prefix, input_text))
        if input_padding:
            rows.append(input_row_text("", ""))
        if self._choices:
            rows.append(truncate_cells("↑↓ move · Enter select · Esc deny · 1/2/3 select", self._columns - 1))
        if self.fullscreen:
            if view_footer:
                if completion_lines:
                    hint = f'↑↓ select · Tab complete · Esc hide · Enter submit ({self._completion_view.selected + 1}/{len(self._completion_view.items)})'
                else:
                    hint = ('Mouse scrolling on · F3 native selection · F2 copy' if self.screen.mouse
                        else 'F2 copy · F3 mouse scrolling')
                rows.append(truncate_cells(hint, self._columns - 1))
            self._history_height = max(1, self._rows - len(rows))
            history = self.transcript.view(self._columns - 1, self._history_height)
            padding = [''] * max(0, self._history_height - len(history))
            rows = history + padding + rows
            input_base += self._history_height
            self.output.write('\x1b[H')
        for index, row in enumerate(rows):
            reset = _RESET_STYLE if colors_enabled(self.output) else ""
            self.output.write(f"{reset}{_CLEAR_LINE}{row}")
            if index < len(rows) - 1:
                self.output.write("\r\n")

        input_row = (
            input_base
            + int(bool(input_padding))
            + cursor_line
        )
        bottom_row = len(rows) - 1
        if bottom_row > input_row:
            self.output.write(f"\x1b[{bottom_row - input_row}A")
        cursor_column = cell_width("❯ ") + cursor_cells
        self.output.write(f"\r\x1b[{cursor_column}C")
        self._live_rows = len(rows)
        self._cursor_live_row = input_row
        self._cursor_column = cursor_column
        self._rendered_rows = tuple(rows)


def _completion_lines(view: CompletionView, width: int, limit: int, color: bool) -> list[str]:
    if not view.items:
        return []
    selected = min(max(0, view.selected), len(view.items) - 1)
    start = max(0, min(selected - limit // 2, len(view.items) - limit))
    lines = []
    for index in range(start, min(len(view.items), start + limit)):
        item = view.items[index]
        text = safe_terminal_text(item.label + ('  ' + item.detail if item.detail else '')).replace('\n', ' ').replace('\t', ' ')
        line = truncate_cells(('❯ ' if index == selected else '  ') + text, width)
        if color and index == selected:
            line = '\x1b[1;36m' + line + _RESET_STYLE
        lines.append(line)
    return lines


def _input_visual_lines(
    text: str,
    cursor: int,
    width: int,
) -> tuple[list[str], int, int]:
    """Wrap editable text while retaining its cursor's visual coordinates."""

    lines: list[list[str]] = [[]]
    widths = [0]
    cursor_position: tuple[int, int] | None = None

    def append_visible(character: str) -> None:
        char_width = cell_width(character)
        if lines[-1] and widths[-1] + char_width > width:
            lines.append([])
            widths.append(0)
        lines[-1].append(character)
        widths[-1] += char_width

    for index, character in enumerate(text):
        if index == cursor:
            cursor_position = len(lines) - 1, widths[-1]
        if character == "\n":
            lines.append([])
            widths.append(0)
        elif character == "\t":
            spaces = 4 - (widths[-1] % 4)
            for _ in range(spaces):
                append_visible(" ")
        elif character.isprintable():
            append_visible(character)

    if cursor_position is None:
        cursor_position = len(lines) - 1, widths[-1]
    return ["".join(line) for line in lines], *cursor_position


def _sanitize_output(text: str) -> str:
    """Keep printable content and SGR styles, but discard cursor controls."""

    pieces: list[str] = []
    position = 0
    for match in _ANSI_ESCAPE.finditer(text):
        pieces.append(text[position : match.start()].replace("\x1b", ""))
        sequence = match.group(0)
        if _SGR_ESCAPE.fullmatch(sequence):
            pieces.append(sequence)
        position = match.end()
    pieces.append(text[position:].replace("\x1b", ""))
    return "".join(pieces)


def _visual_lines(text: str, width: int) -> list[str]:
    lines: list[str] = []
    current: list[str] = []
    used = 0
    active_styles: list[str] = []

    def finish_line() -> None:
        nonlocal current, used
        if active_styles:
            current.append(_RESET_STYLE)
        lines.append("".join(current))
        current = list(active_styles)
        used = 0

    def append_visible(character: str) -> None:
        nonlocal used
        char_width = cell_width(character)
        if used and used + char_width > width:
            finish_line()
        current.append(character)
        used += char_width

    position = 0
    while position < len(text):
        style = _SGR_ESCAPE.match(text, position)
        if style is not None:
            sequence = style.group(0)
            current.append(sequence)
            parameters = sequence[2:-1]
            if _sgr_resets_style(parameters):
                active_styles.clear()
            else:
                active_styles.append(sequence)
            position = style.end()
            continue
        character = text[position]
        position += 1
        if character == "\r":
            continue
        if character == "\n":
            finish_line()
            continue
        if character == "\t":
            for _ in range(4 - (used % 4)):
                append_visible(" ")
            continue
        append_visible(character)
    if used or not lines:
        if active_styles:
            current.append(_RESET_STYLE)
        lines.append("".join(current))
    return lines


def _sgr_resets_style(parameters: str) -> bool:
    if not parameters:
        return True
    return any(
        parameter.isdigit() and int(parameter) == 0
        for parameter in parameters.split(";")
    )


