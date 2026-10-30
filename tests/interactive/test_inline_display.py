"""Inline display behavior and failure contracts."""
from __future__ import annotations
import io
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from fruitfly_agent.interactive.terminal.io.live import InlineTerminalDisplay
from tests.support.terminal import TtyStringIO

ROOT = Path(__file__).resolve().parents[2]


class LineEditorUnitTest(unittest.TestCase):
    def test_permission_choices_move_highlight_without_committing_menu_to_history(self) -> None:
        for no_color in (False, True):
            with self.subTest(no_color=no_color), patch.dict(
                os.environ, {"TERM": "xterm-256color", **({"NO_COLOR": "1"} if no_color else {})}, clear=True,
            ):
                output = TtyStringIO()
                display = InlineTerminalDisplay(output, rows=12, columns=90)
                display.activate()
                labels = ("1. Allow once", "2. Allow reads in /outside for this session", "3. Deny")
                display.set_choices(labels)
                start = len(output.getvalue())
                display.set_choices(labels, selected=1)
                selected = output.getvalue()[start:]
                self.assertIn("❯ 2. Allow reads in /outside for this session", selected)
                self.assertNotIn("❯ 1.", selected)
                self.assertIn("↑↓ move · Enter select · Esc deny", selected)
                if no_color:
                    self.assertNotIn("\x1b[1;36m", selected)
                else:
                    self.assertIn("\x1b[1;36m❯ 2.", selected)
                self.assertEqual(display._pending_output, "")
                display.write("permission: session\n")
                start = len(output.getvalue())
                display.set_choices()
                self.assertNotIn("Allow once", output.getvalue()[start:])
                self.assertIn("❯ ", output.getvalue()[start:])
                self.assertNotIn("╭", output.getvalue()[start:])
                self.assertEqual(output.getvalue().count("permission: session"), 1)
                display.suspend()

    def test_permission_choices_fit_small_terminal_and_keep_selection_visible(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=6, columns=20)
        display.activate()
        display.set_activity("Waiting for permission")
        start = len(output.getvalue())
        display.set_choices(("1. Allow once", "2. Allow for this session", "3. Deny"), selected=2)
        visible = output.getvalue()[start:]
        self.assertIn("❯ 3. Deny", visible)
        self.assertLessEqual(display._live_rows, 6)
        self.assertNotIn("\x1b[2J", visible)
        display.suspend()

    def test_inline_display_redraws_input_after_stream_output(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=10, columns=40)

        display.activate()
        display.set_input("Ｈｉ", 2)
        display.write("assistant> streamed\n")
        display.suspend()

        rendered = output.getvalue()
        stream = rendered.index("assistant> streamed")
        redrawn_input = rendered.index("❯ Ｈｉ", stream)
        self.assertLess(stream, redrawn_input)
        self.assertNotIn("\x1b[H", rendered)
        self.assertNotIn("\x1b[J", rendered)
        self.assertIn("\x1b[?2004h", rendered)
        self.assertIn("\x1b[?2004l", rendered)
        self.assertIn(
            "assistant> streamed\r\n\x1b[2K\r\n\x1b[2K❯ ",
            rendered,
        )
        self.assertIn("\r\x1b[6C", rendered)
        self.assertTrue(
            rendered.endswith("\x1b[2A\r\x1b[?2004l")
        )

    def test_inline_display_expands_multiline_input_frame(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=10, columns=40)
        value = "Ｉｎ\tＯｕ\nＩＤ\tＱｔ"

        display.activate()
        display.set_input(value, len(value))

        rendered = output.getvalue()
        self.assertIn("\x1b[2K❯ Ｉｎ    Ｏｕ\r\n", rendered)
        self.assertIn("\x1b[2K│ ＩＤ    Ｑｔ\r\n\x1b[2K\x1b[1A\r\x1b[14C", rendered)
        self.assertIn("\r\x1b[14C", rendered)

    def test_inline_cursor_column_has_no_extra_gap(self) -> None:
        cases = (
            ("", 0, 2),
            ("abc", 3, 5),
            ("abc", 1, 3),
            ("Ｈｉ", 2, 6),
            ("Ｗa", 1, 4),
        )

        for text, cursor, expected_column in cases:
            with self.subTest(text=text, cursor=cursor):
                output = io.StringIO()
                display = InlineTerminalDisplay(output, rows=10, columns=40)
                display.activate()
                display.set_input(text, cursor)

                self.assertTrue(
                    output.getvalue().endswith(
                        f"\r\x1b[{expected_column}C"
                    )
                )

    def test_inline_display_preserves_sgr_but_drops_foreign_cursor_moves(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=10, columns=40)

        display.activate()
        display.write(
            "\x1b[35m[memory note_lookup]\x1b[0m"
            "\x1b[999;999H\n"
        )

        rendered = output.getvalue()
        self.assertIn("\x1b[35m[memory note_lookup]\x1b[0m", rendered)
        self.assertNotIn("\x1b[999;999H", rendered)

    def test_colored_newline_commits_before_trailing_sgr_reset(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=10, columns=60)

        display.activate()
        display.write("\x1b[36m[tool write] \x1b[0m")
        display.write("\x1b[2mpath=\"page.html\"\n\x1b[0m")

        self.assertEqual(display._pending_output, "")

        display.write("\x1b[36m[tool write done]\x1b[0m")
        display.write("\x1b[2m 21,454 bytes\n\x1b[0m")

        self.assertEqual(display._pending_output, "")
        display.suspend()

    def test_compound_sgr_reset_does_not_leak_style_across_lines(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=10, columns=60)

        display.activate()
        display.write("\x1b[31mred\x1b[39;49;00m\nplain\n")

        self.assertEqual(display._pending_output, "")
        rendered = output.getvalue()
        self.assertIn("\x1b[31mred\x1b[39;49;00m\r\n", rendered)
        self.assertIn("plain\r\n", rendered)
        self.assertNotIn("\x1b[31mplain", rendered)
        display.suspend()

    def test_inline_display_commits_history_once_without_full_screen_redraw(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=8, columns=32)

        display.activate()
        display.set_activity("⠋ Waiting for offline-model · 0.0s")
        for index in range(40):
            display.write(f"history-{index:02d}\n")
        display.set_activity("")
        display.suspend()

        rendered = output.getvalue()
        for index in range(40):
            self.assertEqual(rendered.count(f"history-{index:02d}"), 1)
        self.assertNotIn("\x1b[H", rendered)
        self.assertNotIn("\x1b[J", rendered)
        self.assertNotIn("\x1b[2J", rendered)

    def test_activity_is_separate_from_pending_transcript(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=10, columns=60)

        display.activate()
        display.set_activity("⠋ Waiting for offline-model · 0.0s")

        self.assertEqual(display._pending_output, "")
        self.assertEqual(display._activity, "⠋ Waiting for offline-model · 0.0s")

        display.set_activity("")
        display.suspend()

        self.assertEqual(display._activity, "")

    def test_assistant_preview_is_replaced_and_stable_output_commits_once(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=10, columns=60)
        display.activate()

        display.update_assistant("", "🪰 **partial")
        self.assertEqual(display._assistant_preview, "🪰 **partial")
        self.assertEqual(display._pending_output, "")

        display.update_assistant("🪰 rendered answer\n", "")

        self.assertEqual(display._assistant_preview, "")
        self.assertEqual(display._pending_output, "")
        self.assertEqual(output.getvalue().count("rendered answer"), 1)
        self.assertNotIn("\x1b[H", output.getvalue())
        self.assertNotIn("\x1b[2J", output.getvalue())
        display.suspend()

    def test_resize_refresh_preserves_draft_cursor_and_committed_history(self):
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=14, columns=50)
        display.activate()
        display.write("committed-once\n")
        text = "ＷＸＹＺabcdefgh\nsecond line"
        display.set_input(text, 5)
        for columns in (12, 70, 9, 50):
            display._fixed_columns = columns
            display.refresh()
            self.assertEqual(display._input, text)
            self.assertEqual(display._cursor, 5)
            self.assertEqual(display._columns, columns)
            self.assertLessEqual(display._live_rows, display._rows)
            before = output.getvalue()
            display.refresh()
            self.assertEqual(output.getvalue(), before)
        display.suspend()
        self.assertEqual(output.getvalue().count("committed-once"), 1)
        self.assertNotIn("╭", output.getvalue())
        self.assertNotIn("\x1b[2J", output.getvalue())
