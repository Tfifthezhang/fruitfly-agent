"""Terminal screen lifecycles shared by transient interactive menus."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from typing import TextIO

from .text import is_tty, supports_ansi


@contextmanager
def transient_screen(
    input_stream: TextIO,
    output_stream: TextIO,
) -> Iterator[None]:
    """Keep a full-screen menu out of the main terminal transcript."""

    enabled = is_tty(input_stream) and supports_ansi(output_stream)
    if enabled:
        output_stream.write("\x1b[?1049h\x1b[2J\x1b[H")
        output_stream.flush()
    try:
        yield
    finally:
        if enabled:
            output_stream.write("\x1b[0m\x1b[?1049l")
            output_stream.flush()


__all__ = ["transient_screen"]
