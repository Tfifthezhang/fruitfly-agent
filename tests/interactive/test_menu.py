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
from tests.support.terminal import ScriptedLines, TtyStringIO


class MenuInputTest(unittest.TestCase):
    def test_raw_terminal_keys_map_to_generic_actions(self) -> None:
        for key, action in (
            (b"\x1b[A", MenuAction.UP),
            (b"\x1b[B", MenuAction.DOWN),
            (b" ", MenuAction.TOGGLE),
            (b"\r", MenuAction.ACTIVATE),
            (b"x", MenuAction.IGNORE),
        ):
            with self.subTest(key=key):
                self.assertEqual(RawTerminalMenuInput.decode(key).action, action)

    def test_redirected_input_accepts_numbered_options(self) -> None:
        reader = LineMenuInput(ScriptedLines("3"))

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
        input_stream = TtyStringIO()
        output = TtyStringIO()

        with patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=True):
            with transient_screen(input_stream, output):
                output.write("menu")

        rendered = output.getvalue()
        self.assertTrue(rendered.startswith("\x1b[?1049h\x1b[2J\x1b[H"))
        self.assertIn("menu", rendered)
        self.assertTrue(rendered.endswith("\x1b[0m\x1b[?1049l"))


if __name__ == "__main__":
    unittest.main()
