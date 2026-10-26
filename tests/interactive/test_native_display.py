"""Temporary screen lending preserves native chat output and live drafts."""
import unittest
from fruitfly_agent.interactive.terminal.io.live import InlineTerminalDisplay
from tests.support.terminal import TtyStringIO


class NativeDisplayTests(unittest.TestCase):
    def test_suspended_stream_and_tools_are_buffered_then_committed_once_on_return(self):
        output = TtyStringIO()
        display = InlineTerminalDisplay(output, rows=12, columns=60)
        display.activate()
        display.write('earlier chat\n')
        display.set_input('keep this draft', 4)
        display.update_assistant('', 'unfinished preview')
        display.suspend(preserve_output=True)
        before = output.getvalue()
        display.update_assistant('completed answer\n', '')
        display.write('tool output during menu\n')
        display.set_activity('finished')
        self.assertEqual(before, output.getvalue(), 'chat must not write into a borrowed screen')
        display.activate()
        returned = output.getvalue()[len(before):]
        self.assertIn('completed answer', returned)
        self.assertIn('tool output during menu', returned)
        self.assertNotIn('unfinished preview', returned)
        self.assertIn('keep this draft', returned)
        self.assertEqual(4, display._cursor)
        display.suspend()
        for text in ('earlier chat', 'completed answer', 'tool output during menu'):
            self.assertEqual(1, output.getvalue().count(text))
        self.assertNotIn('\x1b[?1049h', output.getvalue())

    def test_menu_suspension_preserves_an_unfinished_preview_without_committing_it(self):
        output = TtyStringIO()
        display = InlineTerminalDisplay(output, rows=12, columns=60)
        display.activate()
        display.update_assistant('', 'unfinished preview')
        before = len(output.getvalue())
        display.suspend(preserve_output=True)
        self.assertNotIn('unfinished preview', output.getvalue()[before:])
        display.activate()
        display.update_assistant('final complete answer\n', '')
        display.suspend()
        self.assertEqual(1, output.getvalue().count('final complete answer'))
