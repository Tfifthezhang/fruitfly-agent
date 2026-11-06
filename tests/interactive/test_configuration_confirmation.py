"""Shared form navigation redraws selection before an explicit submission."""
import io
from types import SimpleNamespace
import unittest
from fruitfly_agent.interactive.terminal.features.configuration.forms import choose_value, CANCELLED
from fruitfly_agent.interactive.terminal.io.menu import RawTerminalMenuInput, TerminalMenuRenderer, LineMenuInput


class ConfigurationConfirmationTests(unittest.TestCase):
    def test_arrow_navigation_redraws_selection_before_acceptance(self):
        for keys, expected in (((b'\x1b[A', b'\r'), True), ((b'\r',), False),
                               ((b'\x1b[A', b'\x1b[B', b'\r'), False)):
            with self.subTest(keys=keys):
                output = io.StringIO()
                renderer = TerminalMenuRenderer(output); renderer.ansi = True; renderer.color = False
                events = iter(keys)
                quit_requested, value = choose_value(SimpleNamespace(read_event=lambda: RawTerminalMenuInput.decode(next(events))),
                    renderer, title='Confirm configuration', subtitle='', values=(True, False), current=False,
                    labels={True: 'Apply', False: 'Cancel'})
                self.assertFalse(quit_requested)
                self.assertIs(value, expected)
                self.assertIn('Cancel', output.getvalue())
                if b'\x1b[A' in keys:
                    self.assertIn('Apply', output.getvalue())

    def test_numbered_default_remains_cancel_and_back_is_distinct(self):
        for line, expected in (('1', True), ('2', False), ('', False), ('back', CANCELLED)):
            with self.subTest(line=line):
                renderer = TerminalMenuRenderer(io.StringIO()); renderer.numbered = True
                result = choose_value(LineMenuInput(SimpleNamespace(read_line=lambda: line)), renderer,
                    title='Confirm', subtitle='', values=(True, False), current=False)
                self.assertFalse(result[0]); self.assertIs(result[1], expected)
