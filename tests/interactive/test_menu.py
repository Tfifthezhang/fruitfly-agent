"""Generic option-menu behavior for startup configuration."""

from __future__ import annotations

import io
import os
import unittest
from unittest.mock import patch

from fruitfly_agent.interactive.terminal.menu import (
    LineMenuInput,
    MenuAction,
    MenuRow,
    RawTerminalMenuInput,
    TerminalMenuRenderer,
)
from fruitfly_agent.interactive.terminal.screen import transient_screen


class _Lines:
    def __init__(self, *values: str | None) -> None:
        self.values = iter(values)

    def read_line(self) -> str | None:
        return next(self.values)


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class MenuInputTest(unittest.TestCase):
    def test_raw_terminal_keys_map_to_generic_actions(self) -> None:
        self.assertEqual(
            RawTerminalMenuInput.decode(b"\x1b[A").action,
            MenuAction.UP,
        )
        self.assertEqual(
            RawTerminalMenuInput.decode(b"\x1b[B").action,
            MenuAction.DOWN,
        )
        self.assertEqual(
            RawTerminalMenuInput.decode(b" ").action,
            MenuAction.TOGGLE,
        )
        self.assertEqual(
            RawTerminalMenuInput.decode(b"\r").action,
            MenuAction.ACTIVATE,
        )
        self.assertEqual(
            RawTerminalMenuInput.decode(b"x").action,
            MenuAction.IGNORE,
        )

    def test_redirected_input_accepts_numbered_options(self) -> None:
        reader = LineMenuInput(_Lines("3"))

        event = reader.read_event()

        self.assertEqual(event.action, MenuAction.ACTIVATE)
        self.assertEqual(event.index, 2)

    def test_renderer_only_knows_generic_rows(self) -> None:
        output = io.StringIO()
        renderer = TerminalMenuRenderer(output)

        renderer.render(
            title="Choose",
            subtitle="Injected data",
            rows=(
                MenuRow("Alpha", "First", marker="[x]"),
                MenuRow("Beta", "Second"),
            ),
            selected=1,
        )

        rendered = output.getvalue()
        self.assertIn("  1. [x] Alpha", rendered)
        self.assertIn("> 2. Beta", rendered)
        self.assertNotIn("\x1b", rendered)

    def test_transient_screen_restores_main_buffer(self) -> None:
        input_stream = _TtyStringIO()
        output = _TtyStringIO()

        with patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=True):
            with transient_screen(input_stream, output):
                output.write("menu")

        rendered = output.getvalue()
        self.assertTrue(rendered.startswith("\x1b[?1049h\x1b[2J\x1b[H"))
        self.assertIn("menu", rendered)
        self.assertTrue(rendered.endswith("\x1b[0m\x1b[?1049l"))


if __name__ == "__main__":
    unittest.main()
