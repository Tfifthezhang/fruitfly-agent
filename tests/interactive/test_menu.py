"""Generic option-menu behavior for startup configuration."""

from __future__ import annotations

import io
import os
import re
import unittest
from unittest.mock import patch

from fruitfly_agent.interactive.terminal.io.menu import LineMenuInput, MenuAction, MenuEvent, MenuRow, RawTerminalMenuInput, TerminalMenuRenderer, navigate_menu
from fruitfly_agent.interactive.terminal.io.screen import transient_screen
from tests.support.terminal import ScriptedLines, TtyStringIO


class MenuInputTest(unittest.TestCase):
    def test_algorithm_references_wrap_without_truncation_or_extra_selection_indices(self):
        path = 'fruitfly_agent/lab/context_manager/augmentation/information/file_memory/learned.py'
        for color in (False, True):
            with self.subTest(color=color), patch.dict(os.environ, {'TERM': 'xterm-256color',
                    **({} if color else {'NO_COLOR': '1'})}, clear=True), patch(
                    'os.get_terminal_size', return_value=os.terminal_size((38, 24))):
                output = TtyStringIO()
                renderer = TerminalMenuRenderer(output)
                renderer.render(title='Algorithms', subtitle='', selected=0, rows=(
                    MenuRow('Memory', 'Learn from verified practice.', marker='●', depth=1,
                        references=(('Implementation',path),)), MenuRow('Back')))
                plain = re.sub(r'\x1b\[[0-9;]*[mHJK]', '', output.getvalue())
                self.assertIn(path, ''.join(plain.split()))
                self.assertIn('❯   ● Memory', plain)
                self.assertNotIn('…', plain.split('  Back')[0])
                self.assertLessEqual(len(plain.splitlines()),24)

    def test_ansi_hierarchy_distinguishes_focus_enabled_and_changed_without_numbers(self):
        for background in ('15;0', '0;15'):
            for no_color in (False, True):
                with self.subTest(background=background, no_color=no_color), patch.dict(os.environ,
                    {'TERM': 'xterm-256color', 'COLORFGBG': background,
                     **({'NO_COLOR': '1'} if no_color else {})}, clear=True):
                    output = TtyStringIO()
                    renderer = TerminalMenuRenderer(output)
                    renderer.render(title='Context', subtitle='', selected=1, rows=(
                        MenuRow('Enabled capability', marker='[✓]', section='Context augmentation', state='enabled'),
                        MenuRow('Disabled capability', marker='[ ]', section='Context augmentation'),
                        MenuRow('Selected algorithm', marker='●', depth=1, section='Context reduction', state='selected', changed=True)))
                    text = output.getvalue()
                    plain = re.sub(r'\x1b\[[0-9;]*m', '', text)
                    self.assertIn('❯ [ ] Disabled capability', plain)
                    self.assertIn('[✓] Enabled capability', plain)
                    self.assertIn('  ● Selected algorithm · Modified', plain)
                    self.assertEqual(plain.count('Context augmentation'), 1)
                    self.assertNotRegex(plain, r'\d+\. ')
                    if no_color:
                        self.assertNotRegex(text, r'\x1b\[[0-9;]*m')
                    else:
                        self.assertIn('\x1b[32m[✓]', text)
                        self.assertIn('\x1b[1;36m', text)
                        self.assertIn('\x1b[33m · Modified', text)

    def test_small_terminal_keeps_focused_row_and_section_visible_during_inline_input(self):
        output = TtyStringIO()
        with patch.dict(os.environ, {'TERM': 'xterm-256color', 'NO_COLOR': '1'}, clear=True), patch(
            'os.get_terminal_size', return_value=os.terminal_size((38, 18))):
            renderer = TerminalMenuRenderer(output)
            rows = tuple(MenuRow(f'Field {i}', 'Field description', depth=1, section='Algorithm parameters') for i in range(30))
            renderer.render(title='Improvement', subtitle='Draft', rows=rows, selected=25)
            start = len(output.getvalue())
            renderer.begin_input('Field 25\nCurrent: 2\nType: integer\nRange: 1–20')
        frame = output.getvalue()[start:]
        self.assertIn('Improvement', frame)
        self.assertIn('❯   Field 25', frame)
        self.assertIn('Algorithm parameters', frame)
        self.assertIn('Current: 2', frame)
        self.assertNotIn('Field 0\n', frame)
        self.assertLessEqual(len(frame.splitlines()), 18)

    def test_numbered_fallback_numbers_actions_and_keeps_section_headings_unnumbered(self):
        output = io.StringIO()
        TerminalMenuRenderer(output).render(title='Context', subtitle='', selected=1, rows=(
            MenuRow('One', section='Context augmentation'), MenuRow('Two', section='Context reduction')))
        text = output.getvalue()
        self.assertIn('1. One', text)
        self.assertIn('> 2. Two', text)
        self.assertNotIn('1. Context augmentation', text)
        self.assertNotIn('\x1b', text)

    @unittest.skipUnless(os.name == 'posix', 'POSIX terminal control')
    def test_bounded_menu_read_restores_terminal_on_timeout_and_input(self):
        import termios
        master, slave = os.openpty()
        try:
            with os.fdopen(os.dup(slave), 'r') as stream:
                reader = RawTerminalMenuInput(stream)
                original = termios.tcgetattr(slave)
                # macOS may set PENDIN when restoring canonical input. It is
                # kernel queue state, not a changed input/echo mode.
                original[3] &= ~getattr(termios, 'PENDIN', 0)
                def restored():
                    values = termios.tcgetattr(slave)
                    values[3] &= ~getattr(termios, 'PENDIN', 0)
                    return values
                self.assertEqual(reader.poll_event(.01).action, MenuAction.IGNORE)
                self.assertEqual(restored(), original)
                os.write(master, b'\x1b[B')
                self.assertEqual(reader.poll_event(.1).action, MenuAction.DOWN)
                self.assertEqual(restored(), original)
        finally:
            os.close(master)
            os.close(slave)

    def test_shared_navigation_wraps_and_rejects_invalid_numbered_choices(self) -> None:
        for event, selected, expected in (
            (MenuEvent(MenuAction.UP), 0, (2, True)),
            (MenuEvent(MenuAction.DOWN), 2, (0, True)),
            (MenuEvent(MenuAction.ACTIVATE, 1), 0, (1, False)),
            (MenuEvent(MenuAction.ACTIVATE, -1), 1, (1, True)),
            (MenuEvent(MenuAction.ACTIVATE, 3), 1, (1, True)),
            (MenuEvent(MenuAction.BACK), 1, (1, False)),
        ):
            with self.subTest(event=event, selected=selected):
                self.assertEqual(expected, navigate_menu(event, selected, 3))

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
