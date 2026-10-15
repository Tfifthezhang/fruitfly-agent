"""Input emphasis is confined to the editor and remains readable without color."""
import io
import re
import unittest
from unittest.mock import patch

from fruitfly_agent.interactive.terminal.io.live import InlineTerminalDisplay
from fruitfly_agent.interactive.terminal.io.text import cell_width
from fruitfly_agent.interactive.terminal.rendering.renderer import TerminalRenderer
from fruitfly_agent.interactive.terminal.rendering.history import render_history_message
from fruitfly_agent.core.data_model import UserMessage
from tests.support.application import offline_session
from tests.support.terminal import TtyStringIO

SGR = re.compile(r'\x1b\[[0-9;]*m')


class InputEmphasisTests(unittest.TestCase):
    def render(self, hint=None, *, no_color=False, color_term=None, term='xterm-256color'):
        env = {'TERM': term}
        if color_term is not None:
            env['COLORTERM'] = color_term
        if hint is not None:
            env['COLORFGBG'] = hint
        if no_color:
            env['NO_COLOR'] = '1'
        output = TtyStringIO()
        with patch.dict('os.environ', env, clear=True):
            display = InlineTerminalDisplay(output, rows=12, columns=32)
            display.activate()
            display.set_input('甲乙 hello\nsecond', 4)
        return display, output

    def test_editor_has_theme_fill_and_bold_prefix_without_borders(self):
        for hint, fill in (('15;0', '\x1b[48;5;236;39m'), ('0;15', '\x1b[48;5;255;39m'),
                           (None, '\x1b[48;5;236;39m'), ('invalid', '\x1b[48;5;236;39m')):
            with self.subTest(hint=hint):
                display, output = self.render(hint)
                text = output.getvalue()
                self.assertIn(fill, text)
                self.assertNotIn('\x1b[7m', text)
                self.assertRegex(text, r'\x1b\[[0-9;]*1[0-9;]*m❯')
                self.assertIn('❯ 甲乙 hello', SGR.sub('', text))
                self.assertNotIn('╭', text)
                self.assertEqual(len(display._rendered_rows), 4)
                for row in display._rendered_rows:
                    self.assertEqual(cell_width(SGR.sub('', row)), 31)
                    self.assertTrue(row.endswith('\x1b[0m'))

    def test_true_color_uses_neutral_gray_and_preserves_cursor_colors(self):
        for hint, gray in (('15;0', 48), ('0;15', 242), ('0;default;15', 242)):
            with self.subTest(hint=hint):
                _, output = self.render(hint, color_term='truecolor')
                text = output.getvalue()
                self.assertIn(f'\x1b[48;2;{gray};{gray};{gray};39m', text)
                self.assertNotIn('\x1b[46;', text)
                self.assertNotIn('\x1b[30m', text)
                self.assertNotIn('\x1b[7m', text)
                self.assertNotIn('\x1b[97m', text)
                self.assertNotIn('\x1b]12;', text)
                self.assertNotIn('\x1b[?25l', text)

    def test_unknown_theme_defaults_to_dark_and_basic_terminals_use_ansi_gray(self):
        for hint, term, fill in (
            (None, 'xterm-256color', '\x1b[48;5;236;39m'),
            ('custom', 'xterm-256color', '\x1b[48;5;236;39m'),
            ('15;0', 'xterm', '\x1b[100;39m'),
            ('0;15', 'xterm', '\x1b[47;39m'),
        ):
            with self.subTest(hint=hint, term=term):
                _, output = self.render(hint, term=term)
                self.assertIn(fill, output.getvalue())
                self.assertNotIn('\x1b[7m', output.getvalue())
                self.assertNotIn('\x1b[46;', output.getvalue())

    def test_no_color_uses_spacing_without_style_codes(self):
        display, output = self.render(no_color=True)
        self.assertNotRegex(output.getvalue(), SGR)
        self.assertEqual(display._rendered_rows[0], '')
        self.assertEqual(display._rendered_rows[-1], '')
        self.assertIn('❯ 甲乙 hello', display._rendered_rows)

    def test_resize_and_stream_output_keep_fill_out_of_committed_history(self):
        for hint, color_term in (('15;0', None), ('15;0', 'truecolor'), ('0;15', 'truecolor')):
            env = {'TERM': 'xterm-256color', 'COLORFGBG': hint}
            if color_term:
                env['COLORTERM'] = color_term
            with self.subTest(hint=hint, color_term=color_term), patch.dict('os.environ', env, clear=True):
                display, output = self.render(hint, color_term=color_term)
                display.write('assistant-output-once\n')
                for columns in (12, 50, 9, 32):
                    display._fixed_columns = columns
                    display.refresh()
                    self.assertEqual(display._input, '甲乙 hello\nsecond')
                    self.assertEqual(display._cursor, 4)
                    for row in display._rendered_rows:
                        self.assertLessEqual(cell_width(SGR.sub('', row)), columns - 1)
                display.suspend()
            text = output.getvalue()
            self.assertEqual(text.count('assistant-output-once'), 1)
            self.assertIn('\x1b[0m\x1b[2K', text)
            self.assertNotIn('\x1b[2J', text)

    def test_submitted_input_has_accent_spacing_and_no_fill(self):
        for no_color in (False, True):
            with self.subTest(no_color=no_color), patch.dict('os.environ', {
                'TERM': 'xterm-256color', **({'NO_COLOR': '1'} if no_color else {})}, clear=True):
                output = TtyStringIO()
                renderer = TerminalRenderer(output)
                renderer.write_user_input('/improvement\nsecond line')
                text = output.getvalue()
                self.assertEqual(SGR.sub('', text), '\n❯ /improvement\n│ second line\n\n')
                self.assertNotIn('\x1b[7m', text)
                self.assertNotIn('\x1b[100;', text)
                self.assertNotIn('\x1b[48;', text)
                self.assertNotIn('\x1b[46;', text)
                if no_color:
                    self.assertNotRegex(text, SGR)
                else:
                    self.assertRegex(text, r'\x1b\[[0-9;]*1[0-9;]*m❯')

    def test_redirected_echo_is_ansi_free(self):
        output = io.StringIO()
        with patch.dict('os.environ', {'TERM': 'xterm-256color'}, clear=True):
            TerminalRenderer(output).write_user_input('hello')
        self.assertEqual(output.getvalue(), '\n❯ hello\n\n')

    def test_restored_user_label_is_emphasized_without_history_fill(self):
        message = offline_session(messages=[UserMessage('previous question')]).conversation()[0]
        colored = render_history_message(message, columns=40, terminal_ui=True, color=True)
        plain = render_history_message(message, columns=40, terminal_ui=True, color=False)
        self.assertTrue(colored.startswith('\x1b[1mYou\x1b[0m\n'))
        self.assertEqual(SGR.sub('', colored), plain)
        self.assertNotIn('\x1b[7m', colored)
        self.assertNotIn('\x1b[100;', colored)
