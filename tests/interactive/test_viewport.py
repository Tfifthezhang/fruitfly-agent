"""Source-backed display reflow without replaying runtime events."""
import io
import os
import unittest
from unittest.mock import patch

from fruitfly_agent.interactive.contracts.events import AssistantTextDelta
from fruitfly_agent.interactive.terminal.io.live import InlineTerminalDisplay, IsolatedLineEditor
from fruitfly_agent.interactive.terminal.io.text import cell_width, wrap_cells
from fruitfly_agent.interactive.terminal.io.transcript import DisplayTranscript
from fruitfly_agent.interactive.terminal.rendering.renderer import TerminalRenderer
from tests.support.terminal import TtyStringIO, run_finished


class TranscriptTest(unittest.TestCase):
    def test_scroll_anchor_survives_append_and_resize_then_follows_latest(self):
        transcript = DisplayTranscript(wrap_cells)
        transcript.append(''.join(f'row-{i:03d} ' for i in range(40)))
        transcript.scroll(-10, 24, 4)
        before = ''.join(transcript.view(24, 4)).replace(' ', '')
        transcript.append(' more output ' * 20)
        self.assertEqual(''.join(transcript.view(24, 4)).replace(' ', ''), before)
        wider = ''.join(transcript.view(48, 4)).replace(' ', '')
        self.assertIn(before, wider)
        transcript.scroll(None, 48, 4)
        self.assertIn('more output', ''.join(transcript.view(48, 4)))

    def test_formatter_cache_invalidates_on_source_and_width_change(self):
        calls = []
        def format_source(source, width):
            calls.append((source, width))
            return source
        transcript = DisplayTranscript(wrap_cells)
        transcript.update('first', format_source, complete=False)
        transcript.view(20, 4)
        transcript.view(20, 4)
        transcript.view(40, 4)
        transcript.update('first plus second', format_source, complete=True)
        transcript.view(40, 4)
        self.assertEqual(calls, [('first', 20), ('first', 40), ('first plus second', 40)])
        self.assertEqual(len(transcript.records), 1)


class ViewportTest(unittest.IsolatedAsyncioTestCase):
    async def test_completed_markdown_reflows_with_draft_and_menu_restoration(self):
        output = TtyStringIO()
        with patch.object(output, 'fileno', return_value=99), patch.dict(os.environ, {'TERM': 'xterm', 'NO_COLOR': '1'}, clear=True), patch(
            'os.get_terminal_size', return_value=os.terminal_size((32, 18)),
        ) as size:
            display = InlineTerminalDisplay(output, fullscreen=True)
            renderer = TerminalRenderer(display)
            display.activate()
            source = '| Path | Description |\n|---|---|\n| very-long-directory-name | complete-description-value |\n'
            await renderer.render(AssistantTextDelta(run_id='test', text=source))
            await renderer.render(run_finished())
            display.set_input('draft Ａé', 6)
            narrow = '\n'.join(display._rendered_rows)
            self.assertNotIn('very-long-directory-name', narrow)
            size.return_value = os.terminal_size((100, 18))
            display.refresh()
            wider = '\n'.join(display._rendered_rows)
            self.assertIn('very-long-directory-name', wider)
            self.assertIn('complete-description-value', wider)
            self.assertIn('draft Ａé', wider)
            self.assertTrue(all(cell_width(row) <= 99 for row in display._rendered_rows))
            self.assertEqual(display.transcript.records[0].source, source)
            records = len(display.transcript.records)
            display.suspend()
            display.activate()
            self.assertEqual(len(display.transcript.records), records)
            self.assertIn('very-long-directory-name', '\n'.join(display._rendered_rows))
            await renderer.close()
            display.suspend()
        self.assertTrue(output.getvalue().endswith('\x1b[?1049l'))
        self.assertIn('\x1b[?1006l', output.getvalue())
        self.assertNotIn('\x1b[1;', output.getvalue())

    async def test_navigation_does_not_change_editor_draft(self):
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=12, columns=30, fullscreen=True)
        display.activate()
        display.write(''.join(f'line-{i}\n' for i in range(30)))
        editor = IsolatedLineEditor(io.StringIO(), display)
        with patch.object(editor.input, 'fileno', return_value=99), patch.object(editor, 'start'), patch.object(editor, 'stop'), patch(
            'fruitfly_agent.interactive.terminal.io.live.select.select', return_value=([99], [], []),
        ), patch('fruitfly_agent.interactive.terminal.io.live.os.read', side_effect=[b'a', b'\x1b', b'b', b'\r']), patch(
            'fruitfly_agent.interactive.terminal.io.live._read_escape_sequence', return_value=b'\x1b[5~',
        ):
            self.assertEqual(editor.read_line(), 'ab')
        self.assertIsNotNone(display.transcript.anchor)
        self.assertTrue(display.scroll_history(b'\x1b[1;5F'))
        self.assertIsNone(display.transcript.anchor)
        self.assertTrue(display.scroll_history(b'\x1b[<64;1;1M'))
        self.assertIsNotNone(display.transcript.anchor)
        display.suspend()
