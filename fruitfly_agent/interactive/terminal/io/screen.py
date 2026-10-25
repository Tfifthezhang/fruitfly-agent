"""Terminal screen lifecycles shared by transient interactive menus."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from typing import TextIO

from fruitfly_agent.interactive.terminal.io.text import is_tty, supports_ansi


class TerminalScreen:
    """Own screen modes; native mouse selection is the default."""

    def __init__(self, output: TextIO, *, fullscreen: bool, paste: bool = True) -> None:
        self.output, self.fullscreen, self.paste = output, fullscreen, paste
        self.active = False
        self.mouse = False

    def activate(self) -> None:
        if self.active:
            return
        self.active = True
        if self.fullscreen:
            self.output.write('\x1b[?1049h\x1b[2J\x1b[H')
            self.set_mouse(False)
        if self.paste:
            self.output.write('\x1b[?2004h')

    def set_mouse(self, enabled: bool) -> None:
        self.mouse = enabled
        if self.active and self.fullscreen:
            self.output.write('\x1b[?1000h\x1b[?1006h' if enabled else '\x1b[?1006l\x1b[?1000l')

    def suspend(self) -> None:
        if not self.active:
            return
        self.set_mouse(False)
        if self.paste:
            self.output.write('\x1b[?2004l')
        if self.fullscreen:
            self.output.write('\x1b[0m\x1b[?1049l')
        self.output.flush()
        self.active = False


@contextmanager
def transient_screen(
    input_stream: TextIO,
    output_stream: TextIO,
) -> Iterator[None]:
    """Keep a full-screen menu out of the main terminal transcript."""

    enabled = is_tty(input_stream) and supports_ansi(output_stream)
    screen = TerminalScreen(output_stream, fullscreen=True, paste=False)
    if enabled:
        screen.activate()
        output_stream.flush()
    try:
        yield
    finally:
        if enabled:
            screen.suspend()


__all__ = ["TerminalScreen", "transient_screen"]
