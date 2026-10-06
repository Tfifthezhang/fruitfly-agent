"""Concurrent inline transcript and non-canonical terminal editor.

Completed output is appended exactly once so the terminal owns scrollback.  Only
the unfinished output tail and editable prompt form a small live surface that is
redrawn under one lock.  Streamed output and input therefore never share cursor
state, while an update can no longer overwrite already displayed conversation.
"""

from __future__ import annotations

import codecs
import os
import re
import select
import threading
from typing import TextIO

from .text import cell_width, supports_ansi, terminal_columns, truncate_cells


_ANSI_ESCAPE = re.compile(
    r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|[78])"
)
_SGR_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
_CLEAR_LINE = "\x1b[2K"
_RESET_STYLE = "\x1b[0m"
_BRACKETED_PASTE_START = b"\x1b[200~"
_BRACKETED_PASTE_END = b"\x1b[201~"


def prompt_frame_lines(columns: int) -> tuple[str, str]:
    """Return borders that avoid the terminal's auto-wrap column."""

    width = max(4, columns - 1)
    label = "─ prompt "
    if width >= len(label) + 2:
        top = "╭" + label + ("─" * (width - len(label) - 2)) + "╮"
    else:
        top = "╭" + ("─" * (width - 2)) + "╮"
    return top, "╰" + ("─" * (width - 2)) + "╯"


class InlineTerminalDisplay:
    """Append completed output and redraw only the unfinished local surface."""

    def __init__(
        self,
        output: TextIO,
        *,
        rows: int | None = None,
        columns: int | None = None,
    ) -> None:
        self.output = output
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
        self._live_rows = 0
        self._cursor_live_row = 0
        self._lock = threading.RLock()

    @property
    def active(self) -> bool:
        return self._active

    @property
    def encoding(self) -> str | None:
        return getattr(self.output, "encoding", None)

    def isatty(self) -> bool:
        return True

    def fileno(self) -> int:
        return self.output.fileno()

    def write(self, text: str) -> int:
        with self._lock:
            if not self._active:
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
            # Newlines inside a bracketed paste belong to one editable prompt;
            # only an Enter outside the delimiters submits it.
            self.output.write("\x1b[?2004h")
            self._render_live_locked()
            self.output.flush()

    def suspend(self) -> None:
        """Remove the editable frame and leave a normal terminal viewport."""

        with self._lock:
            if not self._active:
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
            self.output.write("\x1b[?2004l")
            self.output.flush()
            self._active = False

    def set_input(self, text: str, cursor: int) -> None:
        with self._lock:
            self._input = text
            self._cursor = min(max(cursor, 0), len(text))
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

    def _measure_locked(self) -> None:
        if self._fixed_rows is not None and self._fixed_columns is not None:
            rows, columns = self._fixed_rows, self._fixed_columns
        else:
            try:
                size = os.get_terminal_size(self.output.fileno())
                rows, columns = size.lines, size.columns
            except (AttributeError, OSError, ValueError):
                rows, columns = 24, terminal_columns(self.output)
        self._rows = max(6, rows)
        self._columns = max(8, columns)

    def _commit_ready_output_locked(self) -> None:
        """Commit every complete logical or visual line to terminal history."""

        if not self._pending_output:
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

        if not self._live_rows:
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

    def _render_live_locked(self) -> None:
        input_width = max(1, self._columns - cell_width("❯ ") - 2)
        all_input_lines, cursor_line, cursor_cells = _input_visual_lines(
            self._input,
            self._cursor,
            input_width,
        )
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
        preview_budget = max(
            0,
            self._rows - len(pending_lines) - len(activity_lines) - 4,
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
            - 3,
        )
        input_start = max(0, cursor_line - max_input_lines + 1)
        input_lines = all_input_lines[input_start : input_start + max_input_lines]
        cursor_line -= input_start

        top, bottom = prompt_frame_lines(self._columns)
        rows: list[str] = [
            *pending_lines,
            *preview_lines,
            *activity_lines,
            top,
        ]
        for index, input_text in enumerate(input_lines, start=input_start):
            prefix = "❯ " if index == 0 else "│ "
            rows.append(f"{prefix}{input_text}")
        rows.append(bottom)
        for index, row in enumerate(rows):
            self.output.write(f"{_RESET_STYLE}{_CLEAR_LINE}{row}")
            if index < len(rows) - 1:
                self.output.write("\r\n")

        input_row = (
            len(pending_lines)
            + len(preview_lines)
            + len(activity_lines)
            + 1
            + cursor_line
        )
        bottom_row = len(rows) - 1
        if bottom_row > input_row:
            self.output.write(f"\x1b[{bottom_row - input_row}A")
        cursor_column = cell_width("❯ ") + cursor_cells
        self.output.write(f"\r\x1b[{cursor_column}C")
        self._live_rows = len(rows)
        self._cursor_live_row = input_row


class IsolatedLineEditor:
    """POSIX non-canonical editor with persistent submission history."""

    def __init__(self, input_stream: TextIO, display: InlineTerminalDisplay) -> None:
        self.input = input_stream
        self.display = display
        self._previous_terminal_state = None
        self._history: list[str] = []

    def start(self) -> None:
        """Enter no-echo character mode while preserving output processing."""

        import termios

        if self._previous_terminal_state is not None:
            return
        descriptor = self.input.fileno()
        previous = termios.tcgetattr(descriptor)
        current = previous.copy()
        current[6] = previous[6].copy()
        current[0] &= ~(
            termios.IXON | termios.ICRNL | termios.INLCR | termios.IGNCR
        )
        current[3] &= ~(
            termios.ECHO | termios.ICANON | termios.IEXTEN | termios.ISIG
        )
        current[6][termios.VMIN] = 1
        current[6][termios.VTIME] = 0
        self._previous_terminal_state = previous
        termios.tcsetattr(descriptor, termios.TCSANOW, current)
        self.display.set_input("", 0)

    def stop(self) -> None:
        """Restore the terminal mode saved by :meth:`start`."""

        import termios

        if self._previous_terminal_state is None:
            return
        descriptor = self.input.fileno()
        previous, self._previous_terminal_state = (
            self._previous_terminal_state,
            None,
        )
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)

    def read_line(self) -> str | None:
        descriptor = self.input.fileno()
        characters: list[str] = []
        cursor = 0
        history_index = len(self._history)
        draft = ""
        encoding = getattr(self.input, "encoding", None) or "utf-8"
        decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
        owns_terminal_state = self._previous_terminal_state is None
        try:
            if owns_terminal_state:
                self.start()
            self.display.set_input("", 0)
            while True:
                first = os.read(descriptor, 1)
                if not first:
                    self.display.set_input("", 0)
                    return None
                if first in {b"\r", b"\n"}:
                    value = "".join(characters)
                    if value and (not self._history or self._history[-1] != value):
                        self._history.append(value)
                    self.display.set_input("", 0)
                    return value
                if first == b"\x03":
                    self.display.set_input("", 0)
                    raise KeyboardInterrupt
                if first == b"\x04":
                    if not characters:
                        self.display.set_input("", 0)
                        return None
                    if cursor < len(characters):
                        del characters[cursor]
                elif first in {b"\x7f", b"\x08"}:
                    if cursor:
                        cursor -= 1
                        del characters[cursor]
                elif first == b"\x01":
                    cursor = 0
                elif first == b"\x05":
                    cursor = len(characters)
                elif first == b"\x15":
                    del characters[:cursor]
                    cursor = 0
                elif first == b"\x17":
                    while cursor and characters[cursor - 1].isspace():
                        cursor -= 1
                        del characters[cursor]
                    while cursor and not characters[cursor - 1].isspace():
                        cursor -= 1
                        del characters[cursor]
                elif first == b"\x1b":
                    sequence = _read_escape_sequence(descriptor, first)
                    if sequence == _BRACKETED_PASTE_START:
                        pasted = _decode_paste(
                            _read_bracketed_paste(descriptor),
                            encoding,
                        )
                        if pasted:
                            characters[cursor:cursor] = pasted
                            cursor += len(pasted)
                    elif sequence in {b"\x1b[A", b"\x1bOA"} and self._history:
                        if history_index == len(self._history):
                            draft = "".join(characters)
                        history_index = max(0, history_index - 1)
                        characters = list(self._history[history_index])
                        cursor = len(characters)
                    elif sequence in {b"\x1b[B", b"\x1bOB"}:
                        if history_index < len(self._history) - 1:
                            history_index += 1
                            characters = list(self._history[history_index])
                        elif history_index == len(self._history) - 1:
                            history_index = len(self._history)
                            characters = list(draft)
                        cursor = len(characters)
                    elif sequence in {b"\x1b[D", b"\x1bOD"}:
                        cursor = max(0, cursor - 1)
                    elif sequence in {b"\x1b[C", b"\x1bOC"}:
                        cursor = min(len(characters), cursor + 1)
                    elif sequence in {b"\x1b[H", b"\x1bOH", b"\x1b[1~"}:
                        cursor = 0
                    elif sequence in {b"\x1b[F", b"\x1bOF", b"\x1b[4~"}:
                        cursor = len(characters)
                    elif sequence == b"\x1b[3~" and cursor < len(characters):
                        del characters[cursor]
                else:
                    decoded = decoder.decode(first, final=False)
                    for character in decoded:
                        if character.isprintable():
                            characters.insert(cursor, character)
                            cursor += 1
                self.display.set_input("".join(characters), cursor)
        finally:
            if owns_terminal_state:
                self.stop()


def create_inline_terminal(
    input_stream: TextIO,
    output_stream: TextIO,
) -> tuple[InlineTerminalDisplay, IsolatedLineEditor] | None:
    """Create the concurrent terminal pair only for a real POSIX ANSI TTY."""

    if os.name != "posix" or not supports_ansi(output_stream):
        return None
    try:
        if not input_stream.isatty():
            return None
        input_stream.fileno()
        output_stream.fileno()
    except (AttributeError, OSError, ValueError):
        return None
    display = InlineTerminalDisplay(output_stream)
    return display, IsolatedLineEditor(input_stream, display)


def _read_escape_sequence(descriptor: int, first: bytes) -> bytes:
    sequence = first
    while len(sequence) < 16 and select.select([descriptor], [], [], 0.02)[0]:
        sequence += os.read(descriptor, 1)
        if sequence[-1:] in b"~ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
            break
    return sequence


def _read_bracketed_paste(descriptor: int) -> bytes:
    """Read paste payload without consuming the following submit key."""

    payload = bytearray()
    while True:
        chunk = os.read(descriptor, 1)
        if not chunk:
            return bytes(payload)
        payload.extend(chunk)
        if payload.endswith(_BRACKETED_PASTE_END):
            del payload[-len(_BRACKETED_PASTE_END) :]
            return bytes(payload)


def _decode_paste(payload: bytes, encoding: str) -> str:
    """Normalize clipboard line endings and drop terminal control bytes."""

    text = payload.decode(encoding, errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(
        character
        for character in text
        if character in {"\n", "\t"} or character.isprintable()
    )


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


__all__ = [
    "IsolatedLineEditor",
    "InlineTerminalDisplay",
    "create_inline_terminal",
    "prompt_frame_lines",
]
