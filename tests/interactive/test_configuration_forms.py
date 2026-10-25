"""Configuration choice fields use metadata and preserve cancellation semantics."""
import io
import unittest

from fruitfly_agent.interactive.terminal.features.configuration.forms import CANCELLED, choose_value
from fruitfly_agent.interactive.terminal.io.menu import LineMenuInput, RawTerminalMenuInput, TerminalMenuRenderer
from tests.support.terminal import ScriptedLines


class ConfigurationChoiceTests(unittest.TestCase):
    def test_numbered_fallback_rejects_free_text_and_returns_declared_value(self):
        output = io.StringIO()
        reader = LineMenuInput(ScriptedLines('made-up-vendor', '2'))
        result = choose_value(reader, TerminalMenuRenderer(output), title='Service', subtitle='Registered choices',
            values=('fixture-one', 'fixture-two'), current='fixture-one')
        self.assertEqual((False, 'fixture-two'), result)
        self.assertIn('fixture-one', output.getvalue())
        self.assertIn('fixture-two', output.getvalue())

    def test_arrows_select_an_injected_option_without_typing_its_name(self):
        events = iter((b'\x1b[B', b'\r'))
        class Keys:
            def read_event(self):
                return RawTerminalMenuInput.decode(next(events))
        result = choose_value(Keys(), TerminalMenuRenderer(io.StringIO()), title='Injected field', subtitle='',
            values=('existing', 'new-extension'), current='existing')
        self.assertEqual((False, 'new-extension'), result)

    def test_cancellation_is_distinct_from_false_null_and_empty_values(self):
        for key, expected in (('1', False), ('2', None), ('3', ''), ('back', CANCELLED)):
            with self.subTest(key=key):
                quit_requested, value = choose_value(LineMenuInput(ScriptedLines(key)), TerminalMenuRenderer(io.StringIO()),
                    title='Typed choices', subtitle='', values=(False, None, ''), current=None)
                self.assertFalse(quit_requested)
                self.assertIs(value, expected)
