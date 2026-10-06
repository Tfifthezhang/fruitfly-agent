"""Responsive and ANSI-safe terminal welcome rendering."""

from __future__ import annotations

import unittest
from dataclasses import replace

from fruitfly_agent.interactive.models import InteractiveStatus
from fruitfly_agent.interactive.terminal.text import cell_width, truncate_cells
from fruitfly_agent.interactive.terminal.welcome import render_welcome


class TerminalTextTest(unittest.TestCase):
    def test_cell_width_handles_wide_and_combining_text(self) -> None:
        self.assertEqual(cell_width("AＷe\u0301🙂"), 6)

    def test_truncate_cells_obeys_the_rendered_width_budget(self) -> None:
        value = truncate_cells("abＨｉ", 5)

        self.assertEqual(value, "abＨ…")
        self.assertEqual(cell_width(value), 5)


class WelcomeRenderingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.status = InteractiveStatus(
            model="offline-model-with-a-deliberately-long-suffix",
            working_directory="/Users/example/research/FruitFlyAgent",
            session_path="session.jsonl",
            message_count=3,
            tool_names=("read", "bash", "edit"),
            mechanisms=("SummarizingCompactor", "HookRegistry"),
        )

    def test_wide_layout_has_fly_wordmark_and_runtime_context(self) -> None:
        rendered = self._render(120)

        self.assertIn("⣀⣈⣷⡴⢦⣾⣁⣀", rendered)
        self.assertIn("⣾⠶⠶⠶⠶⣷", rendered)
        self.assertIn("⠛⠶⠶⠿⠖⠚⠛", rendered)
        self.assertNotIn("●", rendered)
        self.assertIn("████ ███  █  █ ████", rendered)
        self.assertIn("AGENT", rendered)
        self.assertIn("The model organism for agent research.", rendered)
        self.assertIn("2 mechanisms · 3 tools", rendered)
        self.assertIn(
            "Tip: /help for commands · /status for status · /lab for mechanisms",
            rendered,
        )
        self.assertNotIn("View commands", rendered)
        self.assertNotIn("SummarizingCompactor", rendered)
        self.assertNotIn("HookRegistry", rendered)
        self.assertIn("session resumed · 3 messages", rendered)
        self._assert_fits(rendered, 119)

    def test_standard_eighty_column_layout_keeps_original_fly_and_larger_wordmark(self) -> None:
        rendered = self._render(80)

        self.assertIn("⣀⣈⣷⡴⢦⣾⣁⣀", rendered)
        self.assertIn("⠛⠶⠶⠿⠖⠚⠛", rendered)
        self.assertNotIn("●", rendered)
        self.assertIn("████ ███  █  █ ████", rendered)
        self.assertIn("AGENT", rendered)
        self._assert_fits(rendered, 79)

    def test_medium_layout_keeps_larger_wordmark_when_fly_cannot_fit(self) -> None:
        rendered = self._render(70)

        self.assertNotIn("⣀⣈⣷⡴⢦⣾⣁⣀", rendered)
        self.assertIn("████ ███  █  █ ████", rendered)
        self.assertIn("AGENT", rendered)
        self._assert_fits(rendered, 69)

    def test_narrow_layout_is_compact_and_width_safe(self) -> None:
        rendered = self._render(44)

        self.assertIn("✦ FruitFlyAgent", rendered)
        self.assertNotIn("███", rendered)
        self.assertIn("offline-model", rendered)
        self._assert_fits(rendered, 43)

    def test_prompt_identity_is_visible_in_wide_and_compact_layouts(self) -> None:
        self.status = replace(
            self.status,
            prompt_label="Assistant default",
            prompt_hash="sha256:1234567890abcdef",
        )
        wide = self._render(120)
        compact = self._render(44)
        self.assertIn("Assistant default", wide)
        self.assertIn("sha256:12345678", wide)
        self.assertIn("prompt:", compact)
        self._assert_fits(compact, 43)

    def test_non_terminal_output_preserves_the_plain_startup_contract(self) -> None:
        rendered = render_welcome(
            self.status,
            columns=120,
            terminal_ui=False,
            color=True,
        )

        self.assertEqual(
            rendered,
            "FruitFlyAgent interactive · offline-model-with-a-deliberately-long-suffix\n"
            "Type a task, or /help for commands.\n",
        )
        self.assertNotIn("\x1b", rendered)

    def test_color_is_optional_and_does_not_change_content(self) -> None:
        plain = self._render(120)
        colored = render_welcome(
            self.status,
            columns=120,
            terminal_ui=True,
            color=True,
        )

        self.assertNotIn("\x1b", plain)
        self.assertIn("\x1b[1m⢶", colored)
        self.assertIn("\x1b[34m█", colored)

    def _render(self, columns: int) -> str:
        return render_welcome(
            self.status,
            columns=columns,
            terminal_ui=True,
            color=False,
        )

    def _assert_fits(self, rendered: str, width: int) -> None:
        self.assertTrue(
            all(cell_width(line) <= width for line in rendered.splitlines()),
            rendered,
        )


if __name__ == "__main__":
    unittest.main()
