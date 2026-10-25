"""Stable entry points composing terminal display and single-owner input."""
from __future__ import annotations
import os
from typing import TextIO
from .controls import InputInterrupted
from .display import InlineTerminalDisplay, prompt_frame_lines
from .editor import IsolatedLineEditor
from .text import supports_ansi

def create_inline_terminal(
    input_stream: TextIO,
    output_stream: TextIO,
    *, fullscreen: bool = False,
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
    display = InlineTerminalDisplay(output_stream, fullscreen=fullscreen)
    return display, IsolatedLineEditor(input_stream, display)


__all__ = ["InlineTerminalDisplay", "IsolatedLineEditor", "InputInterrupted", "create_inline_terminal", "prompt_frame_lines"]
