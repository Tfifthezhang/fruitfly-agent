"""Native selection, fixed copy views, and one input owner during streaming."""
import io
import os
import unittest
from unittest.mock import patch

from fruitfly_agent.interactive.contracts.events import AssistantTextDelta
from fruitfly_agent.interactive.terminal.io.controls import ViewAction, InputInterrupted
from fruitfly_agent.interactive.terminal.io.live import InlineTerminalDisplay, IsolatedLineEditor
from fruitfly_agent.interactive.terminal.rendering.renderer import TerminalRenderer
from tests.support.terminal import TtyStringIO, run_finished


class CopyViewTests(unittest.IsolatedAsyncioTestCase):
    def display(self):
        output = TtyStringIO()
        display = InlineTerminalDisplay(output, rows=12, columns=50, fullscreen=True)
        display.activate()
        self.addCleanup(display.suspend)
        return display, output

    def test_native_selection_default_and_explicit_mouse_capture_restore(self):
        display, output = self.display()
        self.assertNotIn('\x1b[?1000h', output.getvalue())
        self.assertNotIn('\x1b[?1006h', output.getvalue())
        display.handle_action(ViewAction.TOGGLE_MOUSE)
        self.assertIn('\x1b[?1000h', output.getvalue())
        self.assertIn('Mouse scrolling on', output.getvalue())
        display.handle_action(ViewAction.TOGGLE_COPY)
        self.assertFalse(display.screen.mouse)
        display.handle_action(ViewAction.EXIT_COPY)
        self.assertTrue(display.screen.mouse)
        display.handle_action(ViewAction.TOGGLE_MOUSE)
        self.assertFalse(display.screen.mouse)
        display.suspend()
        self.assertTrue(output.getvalue().endswith('\x1b[0m\x1b[?1049l'))
        display.activate()
        self.assertFalse(display.screen.mouse)

    async def test_streaming_and_activity_continue_without_repainting_copy_view(self):
        with patch.dict(os.environ, {'TERM': 'xterm', 'NO_COLOR': '1'}, clear=True):
            display, output = self.display()
            renderer = TerminalRenderer(display)
            await renderer.render(AssistantTextDelta(run_id='run-1', text='original answer'))
            display.set_input('draft Ａé', 5)
            display.handle_action(ViewAction.TOGGLE_COPY)
            frozen = output.getvalue()
            await renderer.render(AssistantTextDelta(run_id='run-1', text=' plus new evidence'))
            display.set_activity('still running')
            await renderer.render(run_finished())
            self.assertEqual(frozen, output.getvalue())
            self.assertTrue(display.copying)
            display.handle_action(ViewAction.EXIT_COPY)
            self.assertIn('original answer plus new evidence', '\n'.join(display._rendered_rows))
            self.assertIn('draft Ａé', '\n'.join(display._rendered_rows))
            self.assertFalse(display.copying)
            await renderer.close()

    def test_frozen_history_can_page_without_new_output_changing_its_rows(self):
        display, output = self.display()
        display.write(''.join(f'row-{i:03d}\n' for i in range(40)))
        display.handle_action(ViewAction.TOGGLE_COPY)
        display.handle_action(ViewAction.PAGE_UP)
        rows = display._rendered_rows
        display.write('new output\n' * 30)
        self.assertEqual(rows, display._rendered_rows)
        display.handle_action(ViewAction.PAGE_DOWN)
        self.assertNotIn('new output', '\n'.join(display._rendered_rows))
        display.handle_action(ViewAction.EXIT_COPY)
        self.assertIn('new output', '\n'.join(display._rendered_rows))

    def test_resize_and_required_choices_end_copy_without_changing_the_draft(self):
        output = TtyStringIO()
        with patch.object(output, 'fileno', return_value=99), patch('os.get_terminal_size',
                return_value=os.terminal_size((60, 20))) as size:
            display = InlineTerminalDisplay(output, fullscreen=True)
            display.activate()
            self.addCleanup(display.suspend)
            display.set_input('keep this draft', 4)
            display.handle_action(ViewAction.TOGGLE_COPY)
            size.return_value = os.terminal_size((30, 12))
            display.refresh()
            self.assertFalse(display.copying)
            self.assertIn('keep this draft', '\n'.join(display._rendered_rows))
            display.handle_action(ViewAction.TOGGLE_COPY)
            display.set_choices(('Allow once', 'Deny'))
            self.assertFalse(display.copying)
            self.assertIn('Allow once', '\n'.join(display._rendered_rows))
            self.assertTrue(display.handle_action(ViewAction.TOGGLE_COPY))
            self.assertFalse(display.copying, 'required choices must stay visible')

    def test_copy_controls_do_not_submit_or_modify_the_editor_draft(self):
        display, output = self.display()
        editor = IsolatedLineEditor(io.StringIO(), display)
        # F2 enters copy; printable text and Enter are ignored; Esc returns to the draft.
        with patch.object(editor.input, 'fileno', return_value=99), patch.object(editor, 'start'), patch.object(editor, 'stop'), patch(
            'fruitfly_agent.interactive.terminal.io.editor.select.select', return_value=([99], [], [])), patch(
            'fruitfly_agent.interactive.terminal.io.editor.os.read', side_effect=[b'a', b'\x1b', b'x', b'\r', b'\x1b', b'b', b'\r']), patch(
            'fruitfly_agent.interactive.terminal.io.editor._read_escape_sequence', side_effect=[b'\x1bOQ', b'\x1b']):
            self.assertEqual('ab', editor.read_line())
        self.assertFalse(display.copying)

    def test_interrupt_and_screen_lending_release_copy_state_and_mouse(self):
        display, output = self.display()
        editor = IsolatedLineEditor(io.StringIO(), display)
        display.handle_action(ViewAction.TOGGLE_COPY)
        with patch.object(editor.input, 'fileno', return_value=99), patch.object(editor, 'start'), patch.object(editor, 'stop'), patch(
            'fruitfly_agent.interactive.terminal.io.editor.select.select', return_value=([99], [], [])), patch(
            'fruitfly_agent.interactive.terminal.io.editor.os.read', return_value=b'\x03'), self.assertRaises(InputInterrupted):
            editor.read_line()
        self.assertFalse(display.copying)
        display.handle_action(ViewAction.TOGGLE_COPY)
        display.suspend()
        display.activate()
        self.assertFalse(display.copying)
        self.assertFalse(display.screen.mouse)


@unittest.skipUnless(os.name == 'posix', 'requires a POSIX PTY')
class CopyViewPtyTests(unittest.TestCase):
    def test_real_f2_escape_and_streaming_preserve_the_submitted_draft(self):
        import select
        import struct
        import subprocess
        import sys
        import termios
        import time
        import fcntl
        master, slave = os.openpty()
        command_read, command_write = os.pipe()
        ack_read, ack_write = os.pipe()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
        original = termios.tcgetattr(slave)
        script = '''
import os, sys, threading
from fruitfly_agent.interactive.terminal.io.live import InlineTerminalDisplay, IsolatedLineEditor
screen = InlineTerminalDisplay(sys.stdout, fullscreen=True)
editor = IsolatedLineEditor(sys.stdin, screen)
def background():
    os.read(int(sys.argv[1]), 1)
    screen.write('arrived-in-background\\n')
    screen.set_activity('background finished')
    os.write(int(sys.argv[2]), b'done')
editor.start()
screen.activate()
screen.write('initial-visible\\n')
producer = threading.Thread(target=background)
producer.start()
try:
    value = editor.read_line()
finally:
    screen.suspend()
    editor.stop()
producer.join(timeout=2)
print('RESULT:' + str(value), flush=True)
'''
        received = bytearray()
        process = None
        try:
            process = subprocess.Popen([sys.executable, '-c', script, str(command_read), str(ack_write)],
                stdin=slave, stdout=slave, stderr=slave, pass_fds=(command_read, ack_write),
                env={**os.environ, 'TERM': 'xterm', 'NO_COLOR': '1'})
            def until(marker):
                chunk = bytearray()
                deadline = time.monotonic() + 4
                while marker not in chunk:
                    remaining = deadline - time.monotonic()
                    self.assertGreater(remaining, 0, bytes(received + chunk).decode(errors='replace'))
                    if select.select([master], [], [], remaining)[0]:
                        chunk.extend(os.read(master, 65536))
                received.extend(chunk)
            until(b'initial-visible')
            os.write(master, b'draft')
            until(b'draft')
            os.write(master, b'\x1bOQ')
            until(b'Copy:')
            os.write(master, b'ignored\r')
            os.write(command_write, b'u')
            self.assertTrue(select.select([ack_read], [], [], 4)[0])
            self.assertEqual(b'done', os.read(ack_read, 4))
            self.assertFalse(select.select([master], [], [], .05)[0], 'background updates must not redraw the copy view')
            os.write(master, b'\x1b')
            until(b'arrived-in-background')
            os.write(master, b'\r')
            until(b'RESULT:draft')
            self.assertEqual(0, process.wait(timeout=4))
            self.assertNotIn(b'\x1b[?1000h', received)
            self.assertIn(b'\x1b[?1049l', received)
            restored = termios.tcgetattr(slave)
            # macOS sets PENDIN while restoring canonical input; it is pending
            # input status, independent of the modes owned by the editor.
            pending = getattr(termios, 'PENDIN', 0)
            original[3] &= ~pending
            restored[3] &= ~pending
            self.assertEqual(original, restored)
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            for descriptor in (master, slave, command_read, command_write, ack_read, ack_write):
                os.close(descriptor)
