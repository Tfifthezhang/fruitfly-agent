"""Terminal Markdown rendering stays semantic, safe and stream-friendly."""

from __future__ import annotations

import re
import unittest

from fruitfly_agent.interactive.terminal.markdown import (
    MarkdownStreamPresenter,
    TerminalMarkdownRenderer,
)


ANSI = re.compile(r"\x1b\[[0-9;]*m")


class TerminalMarkdownRendererTest(unittest.TestCase):
    def test_common_elements_render_without_source_markers(self) -> None:
        source = """# Root cause

**Fix** the `integrity` value.

- first
- second

> quoted detail

[Docs](https://example.test)
"""

        rendered = TerminalMarkdownRenderer(color=False).render(source)

        self.assertIn("◆ Root cause", rendered)
        self.assertIn("Fix the integrity value.", rendered)
        self.assertIn("• first", rendered)
        self.assertIn("│ quoted detail", rendered)
        self.assertIn("Docs (https://example.test)", rendered)
        self.assertNotIn("**", rendered)
        self.assertNotIn("`integrity`", rendered)
        self.assertNotIn("# Root cause", rendered)

    def test_color_uses_semantic_sgr_styles(self) -> None:
        rendered = TerminalMarkdownRenderer(color=True).render(
            "## Heading\n\n**bold** and `code`\n"
        )

        self.assertIn("\x1b[1;34mHeading\x1b[0m", rendered)
        self.assertIn("\x1b[1mbold\x1b[0m", rendered)
        self.assertIn("\x1b[36mcode\x1b[0m", rendered)

    def test_fenced_code_is_highlighted_without_fence_markers(self) -> None:
        rendered = TerminalMarkdownRenderer(color=True).render(
            "```python\nprint(1)\n```\n"
        )

        self.assertIn("  python", ANSI.sub("", rendered))
        self.assertIn("    print(1)", ANSI.sub("", rendered))
        self.assertNotIn("```", rendered)
        self.assertIn("\x1b[", rendered)

    def test_table_aligns_wide_characters_and_degrades_on_narrow_width(self) -> None:
        source = """| Name | Count |
|---|---:|
| Ｈｉ | 2 |
"""

        table = TerminalMarkdownRenderer(columns=40, color=False).render(source)
        records = TerminalMarkdownRenderer(columns=10, color=False).render(source)

        self.assertIn("┌", table)
        self.assertIn("│ Ｈｉ", table)
        self.assertIn("Name: Ｈｉ", records)
        self.assertIn("Count: 2", records)

    def test_model_control_sequences_are_removed_before_styling(self) -> None:
        rendered = TerminalMarkdownRenderer(color=True).render(
            "**safe**\x1b[2J\x1b[999;999H text\n"
        )

        self.assertIn("safe", rendered)
        self.assertIn("text", rendered)
        self.assertNotIn("\x1b[2J", rendered)
        self.assertNotIn("\x1b[999;999H", rendered)


class MarkdownStreamPresenterTest(unittest.TestCase):
    def test_split_markers_across_deltas_commit_clean_markdown_once(self) -> None:
        presenter = MarkdownStreamPresenter(color=False)
        committed: list[str] = []

        for character in "**Root cause**: `bad.css`\n\nNext paragraph":
            update = presenter.feed(character)
            committed.append(update.committed)
        committed.append(presenter.flush().committed)
        output = "".join(committed)

        self.assertEqual(output.count("Root cause"), 1)
        self.assertEqual(output.count("bad.css"), 1)
        self.assertIn("Next paragraph", output)
        self.assertNotIn("**", output)
        self.assertNotIn("`bad.css`", output)

    def test_open_code_fence_remains_preview_until_closed(self) -> None:
        presenter = MarkdownStreamPresenter(color=False)

        opening = presenter.feed("```python\nprint(1)\n")
        closing = presenter.feed("```\n")

        self.assertEqual(opening.committed, "")
        self.assertIn("print(1)", opening.preview)
        self.assertIn("print(1)", closing.committed)
        self.assertEqual(closing.preview, "")


if __name__ == "__main__":
    unittest.main()

