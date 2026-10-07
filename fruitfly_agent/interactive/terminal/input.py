"""Fallback and configuration-menu line editing.

Configuration screens can delegate cursor movement and text editing to Python's
stdlib readline integration. Redirected streams keep a deterministic, ANSI-free
fallback. Concurrent Agent input lives in ``terminal.live`` so streamed output
never shares readline's cursor.
"""

from __future__ import annotations

import builtins
import importlib
import locale
import os
import sys
from types import ModuleType
from typing import Protocol, TextIO

from .live import prompt_frame_lines
from .text import is_tty, supports_ansi, terminal_columns


class LineEditor(Protocol):
    """Return one submitted line, or None when the input reaches EOF."""

    def read_line(self) -> str | None: ...


class StreamLineEditor:
    """Plain line reader for redirected streams and deterministic tests."""

    def __init__(
        self,
        input_stream: TextIO,
        output_stream: TextIO,
        *,
        prompt: str = "you> ",
    ) -> None:
        self.input = input_stream
        self.output = output_stream
        self.prompt = prompt

    def read_line(self) -> str | None:
        self.output.write(self.prompt)
        self.output.flush()
        line = self.input.readline()
        return None if line == "" else line


class ReadlineLineEditor:
    """Framed TTY input backed by the platform's Python readline module."""

    _CLEAR_LINE = "\x1b[2K"
    _MOVE_UP = "\x1b[1A"
    _MOVE_DOWN = "\x1b[1B"

    def __init__(
        self,
        output_stream: TextIO,
        *,
        reader=builtins.input,
        prompt: str = "❯ ",
        framed: bool = True,
    ) -> None:
        self.output = output_stream
        self.reader = reader
        self.prompt = prompt
        self.framed = framed
        self.frame_label = "prompt"

    def read_line(self) -> str | None:
        if not self.framed:
            try:
                return self.reader("you> " if self.frame_label == "prompt" else f"{self.frame_label}> ")
            except EOFError:
                return None
        top, bottom = self._frame_lines(self._terminal_columns(), self.frame_label)
        self.output.write(f"{top}\n\n{bottom}{self._MOVE_UP}\r")
        self.output.flush()
        try:
            value = self.reader(self.prompt)
        except EOFError:
            self._finish_without_advanced_line(bottom)
            return None
        except BaseException:
            self._finish_after_interruption(bottom)
            raise
        self._finish_after_submitted_line(bottom)
        return value

    def _terminal_columns(self) -> int:
        return terminal_columns(self.output)

    @staticmethod
    def _frame_lines(columns: int, label: str = "prompt") -> tuple[str, str]:
        return prompt_frame_lines(columns, label)

    def _finish_after_submitted_line(self, bottom: str) -> None:
        self.output.write(f"\r{self._CLEAR_LINE}{bottom}\n")
        self.output.flush()

    def _finish_without_advanced_line(self, bottom: str) -> None:
        self.output.write(
            f"\r{self._CLEAR_LINE}{bottom}"
            f"{self._MOVE_DOWN}\r{self._CLEAR_LINE}"
        )
        self.output.flush()

    def _finish_after_interruption(self, bottom: str) -> None:
        self.output.write(f"\r{self._CLEAR_LINE}{bottom}\n")
        self.output.flush()


def read_field_line(editor: LineEditor, label: str) -> str | None:
    """Label built-in form readers without changing the injected reader contract."""
    if isinstance(editor, ReadlineLineEditor):
        previous = editor.frame_label
        editor.frame_label = label
        try:
            return editor.read_line()
        finally:
            editor.frame_label = previous
    if isinstance(editor, StreamLineEditor):
        previous = editor.prompt
        editor.prompt = f"{label}> "
        try:
            return editor.read_line()
        finally:
            editor.prompt = previous
    return editor.read_line()


def create_line_editor(
    input_stream: TextIO,
    output_stream: TextIO,
) -> LineEditor:
    """Choose enhanced editing only for the process's real TTY streams."""
    if (
        input_stream is sys.stdin
        and output_stream is sys.stdout
        and is_tty(input_stream)
        and is_tty(output_stream)
        and _enable_stdlib_readline(input_stream)
    ):
        return ReadlineLineEditor(
            output_stream,
            framed=supports_ansi(output_stream),
        )
    return StreamLineEditor(input_stream, output_stream)


def _enable_stdlib_readline(input_stream: TextIO) -> bool:
    """Load readline lazily and prefer horizontal scrolling for the frame."""
    _align_ctype_with_stream_encoding(input_stream)
    try:
        module = importlib.import_module("readline")
    except ImportError:
        return False
    if _is_gnu_readline(module):
        try:
            module.parse_and_bind("set horizontal-scroll-mode on")
        except (AttributeError, ValueError):
            pass
    return True


def _align_ctype_with_stream_encoding(input_stream: TextIO) -> None:
    """Let readline treat UTF-8 input as multibyte text when LC_CTYPE is C."""
    encoding = (
        (getattr(input_stream, "encoding", "") or "")
        .replace("-", "")
        .lower()
    )
    if encoding not in {"utf8", "utf_8"} or _ctype_is_utf8():
        return
    original = locale.setlocale(locale.LC_CTYPE)
    candidates = (
        os.environ.get("LC_CTYPE"),
        os.environ.get("LANG"),
        "C.UTF-8",
        "UTF-8",
        "en_US.UTF-8",
    )
    for candidate in candidates:
        if not candidate or candidate in {"C", "POSIX"}:
            continue
        try:
            locale.setlocale(locale.LC_CTYPE, candidate)
        except locale.Error:
            continue
        if _ctype_is_utf8():
            return
    locale.setlocale(locale.LC_CTYPE, original)


def _ctype_is_utf8() -> bool:
    try:
        codeset = locale.nl_langinfo(locale.CODESET)
    except (AttributeError, ValueError):
        return False
    return codeset.replace("-", "").lower() == "utf8"


def _is_gnu_readline(module: ModuleType) -> bool:
    backend = getattr(module, "backend", None)
    if backend is not None:
        return backend == "readline"
    return "GNU readline" in (getattr(module, "__doc__", "") or "")


__all__ = [
    "LineEditor",
    "ReadlineLineEditor",
    "StreamLineEditor",
    "create_line_editor",
]
