"""Terminal Markdown rendering stays semantic, safe and stream-friendly."""

from __future__ import annotations

import re
import unittest

from fruitfly_agent.interactive.terminal.rendering.markdown import MarkdownStreamPresenter, TerminalMarkdownRenderer
from fruitfly_agent.interactive.terminal.io.text import cell_width


ANSI = re.compile(r"\x1b\[[0-9;]*m")


class TerminalMarkdownRendererTest(unittest.TestCase):
    def test_long_table_cells_preserve_all_text_at_every_width(self):
        path = '/workspace/very-long-directory/complete-file-name.jsonl'
        detail = '完整说明éＡＢand-all-remaining-content'
        source = f'| Path | Detail |\n|---|---|\n| {path} | {detail} |\n'
        for width in (8, 20, 40, 79, 120):
            with self.subTest(width=width):
                rendered = TerminalMarkdownRenderer(columns=width, color=False).render(source)
                self.assertNotIn('…', rendered)
                self.assertTrue(all(cell_width(line) <= width for line in rendered.splitlines()))
                if '┌' in rendered:
                    rows = [line.split('│')[1:-1] for line in rendered.splitlines() if line.startswith('│')]
                    self.assertEqual(''.join(row[0].strip() for row in rows), 'Path' + path)
                    self.assertEqual(''.join(row[1].strip() for row in rows), 'Detail' + detail)
                else:
                    compact = ''.join(rendered.split())
                    self.assertIn(path, compact)
                    self.assertIn(detail, compact)

    def test_paragraph_soft_breaks_reflow_but_hard_breaks_remain(self):
        renderer = TerminalMarkdownRenderer(color=False)
        self.assertIn('one two', renderer.render('one\ntwo'))
        self.assertIn('one\ntwo', renderer.render('one  \ntwo'))

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

