"""Generic option-menu input and rendering for terminal frontends."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
import select
from typing import Protocol, TextIO

from .input import LineEditor
from .text import colors_enabled, is_tty, supports_ansi


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
class MenuRow:
    label: str
    detail: str = ""
    marker: str = ""


class RawTerminalMenuInput:
    """Read one POSIX terminal key while restoring terminal state every time."""

    def __init__(self, input_stream: TextIO) -> None:
        self.input = input_stream

    def read_event(self) -> MenuEvent:
        import termios
        import tty

        descriptor = self.input.fileno()
        previous = termios.tcgetattr(descriptor)
        try:
            tty.setraw(descriptor)
            first = os.read(descriptor, 1)
            if not first or first == b"\x04":
                return MenuEvent(MenuAction.QUIT)
            if first == b"\x03":
                raise KeyboardInterrupt
            sequence = first
            if first == b"\x1b":
                while len(sequence) < 8 and select.select(
                    [descriptor], [], [], 0.02
                )[0]:
                    sequence += os.read(descriptor, 1)
            return self.decode(sequence)
        finally:
            termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)

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
        self._rendered = False

    def render(
        self,
        *,
        title: str,
        subtitle: str,
        rows: tuple[MenuRow, ...],
        selected: int,
        notice: str = "",
        instructions: str = "↑↓ move · Enter select · Space toggle · Esc back · q quit",
    ) -> None:
        if self.ansi:
            self.output.write("\x1b[2J\x1b[H")
        elif self._rendered:
            self.output.write("\n")
        self._rendered = True
        self.output.write(f"{title}\n\n{subtitle}\n\n")
        for index, row in enumerate(rows):
            cursor = ">" if index == selected else " "
            marker = f"{row.marker} " if row.marker else ""
            label = f"{index + 1}. {marker}{row.label}"
            if self.color and index == selected:
                label = f"\x1b[1;36m{label}\x1b[0m"
            self.output.write(f"{cursor} {label}\n")
            if row.detail:
                detail = row.detail
                if self.color and index != selected:
                    detail = f"\x1b[2m{detail}\x1b[0m"
                self.output.write(f"     {detail}\n")
        if notice:
            self.output.write(f"\n{notice}\n")
        self.output.write(f"\n{instructions}\n")
        self.output.flush()


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
    "RawTerminalMenuInput",
    "TerminalMenuRenderer",
    "create_menu_input",
]


def navigate_menu(event, selected: int, size: int):
    if event.index is not None:
        return (event.index, False) if 0 <= event.index < size else (selected, True)
    if event.action == MenuAction.UP:
        return (selected - 1) % size, True
    if event.action == MenuAction.DOWN:
        return (selected + 1) % size, True
    return selected, False

