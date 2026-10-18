"""TTY editing regressions for the lightweight interactive frontend."""

from __future__ import annotations

import errno
import io
import os
import pty
import re
import select
import signal
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fruitfly_agent.interactive.terminal.io.input import ReadlineLineEditor, StreamLineEditor, create_line_editor, read_field_line
from fruitfly_agent.interactive.terminal.io.live import InlineTerminalDisplay
from tests.support.terminal import TtyStringIO


ROOT = Path(__file__).resolve().parents[2]


class LineEditorUnitTest(unittest.TestCase):
    def test_permission_choices_move_highlight_without_committing_menu_to_history(self) -> None:
        for no_color in (False, True):
            with self.subTest(no_color=no_color), patch.dict(
                os.environ, {"TERM": "xterm-256color", **({"NO_COLOR": "1"} if no_color else {})}, clear=True,
            ):
                output = TtyStringIO()
                display = InlineTerminalDisplay(output, rows=12, columns=90)
                display.activate()
                labels = ("1. Allow once", "2. Allow reads in /outside for this session", "3. Deny")
                display.set_choices(labels)
                start = len(output.getvalue())
                display.set_choices(labels, selected=1)
                selected = output.getvalue()[start:]
                self.assertIn("❯ 2. Allow reads in /outside for this session", selected)
                self.assertNotIn("❯ 1.", selected)
                self.assertIn("↑↓ move · Enter select · Esc deny", selected)
                if no_color:
                    self.assertNotIn("\x1b[1;36m", selected)
                else:
                    self.assertIn("\x1b[1;36m❯ 2.", selected)
                self.assertEqual(display._pending_output, "")
                display.write("permission: session\n")
                start = len(output.getvalue())
                display.set_choices()
                self.assertNotIn("Allow once", output.getvalue()[start:])
                self.assertIn("❯ ", output.getvalue()[start:])
                self.assertNotIn("╭", output.getvalue()[start:])
                self.assertEqual(output.getvalue().count("permission: session"), 1)
                display.suspend()

    def test_permission_choices_fit_small_terminal_and_keep_selection_visible(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=6, columns=20)
        display.activate()
        display.set_activity("Waiting for permission")
        start = len(output.getvalue())
        display.set_choices(("1. Allow once", "2. Allow for this session", "3. Deny"), selected=2)
        visible = output.getvalue()[start:]
        self.assertIn("❯ 3. Deny", visible)
        self.assertLessEqual(display._live_rows, 6)
        self.assertNotIn("\x1b[2J", visible)
        display.suspend()

    def test_inline_display_redraws_input_after_stream_output(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=10, columns=40)

        display.activate()
        display.set_input("Ｈｉ", 2)
        display.write("assistant> streamed\n")
        display.suspend()

        rendered = output.getvalue()
        stream = rendered.index("assistant> streamed")
        redrawn_input = rendered.index("❯ Ｈｉ", stream)
        self.assertLess(stream, redrawn_input)
        self.assertNotIn("\x1b[H", rendered)
        self.assertNotIn("\x1b[J", rendered)
        self.assertIn("\x1b[?2004h", rendered)
        self.assertIn("\x1b[?2004l", rendered)
        self.assertIn(
            "assistant> streamed\r\n\x1b[2K\r\n\x1b[2K❯ ",
            rendered,
        )
        self.assertIn("\r\x1b[6C", rendered)
        self.assertTrue(
            rendered.endswith("\x1b[2A\r\x1b[?2004l")
        )

    def test_inline_display_expands_multiline_input_frame(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=10, columns=40)
        value = "Ｉｎ\tＯｕ\nＩＤ\tＱｔ"

        display.activate()
        display.set_input(value, len(value))

        rendered = output.getvalue()
        self.assertIn("\x1b[2K❯ Ｉｎ    Ｏｕ\r\n", rendered)
        self.assertIn("\x1b[2K│ ＩＤ    Ｑｔ\r\n\x1b[2K\x1b[1A\r\x1b[14C", rendered)
        self.assertIn("\r\x1b[14C", rendered)

    def test_inline_cursor_column_has_no_extra_gap(self) -> None:
        cases = (
            ("", 0, 2),
            ("abc", 3, 5),
            ("abc", 1, 3),
            ("Ｈｉ", 2, 6),
            ("Ｗa", 1, 4),
        )

        for text, cursor, expected_column in cases:
            with self.subTest(text=text, cursor=cursor):
                output = io.StringIO()
                display = InlineTerminalDisplay(output, rows=10, columns=40)
                display.activate()
                display.set_input(text, cursor)

                self.assertTrue(
                    output.getvalue().endswith(
                        f"\r\x1b[{expected_column}C"
                    )
                )

    def test_inline_display_preserves_sgr_but_drops_foreign_cursor_moves(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=10, columns=40)

        display.activate()
        display.write(
            "\x1b[35m[memory note_lookup]\x1b[0m"
            "\x1b[999;999H\n"
        )

        rendered = output.getvalue()
        self.assertIn("\x1b[35m[memory note_lookup]\x1b[0m", rendered)
        self.assertNotIn("\x1b[999;999H", rendered)

    def test_colored_newline_commits_before_trailing_sgr_reset(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=10, columns=60)

        display.activate()
        display.write("\x1b[36m[tool write] \x1b[0m")
        display.write("\x1b[2mpath=\"page.html\"\n\x1b[0m")

        self.assertEqual(display._pending_output, "")

        display.write("\x1b[36m[tool write done]\x1b[0m")
        display.write("\x1b[2m 21,454 bytes\n\x1b[0m")

        self.assertEqual(display._pending_output, "")
        display.suspend()

    def test_compound_sgr_reset_does_not_leak_style_across_lines(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=10, columns=60)

        display.activate()
        display.write("\x1b[31mred\x1b[39;49;00m\nplain\n")

        self.assertEqual(display._pending_output, "")
        rendered = output.getvalue()
        self.assertIn("\x1b[31mred\x1b[39;49;00m\r\n", rendered)
        self.assertIn("plain\r\n", rendered)
        self.assertNotIn("\x1b[31mplain", rendered)
        display.suspend()

    def test_inline_display_commits_history_once_without_full_screen_redraw(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=8, columns=32)

        display.activate()
        display.set_activity("⠋ Waiting for offline-model · 0.0s")
        for index in range(40):
            display.write(f"history-{index:02d}\n")
        display.set_activity("")
        display.suspend()

        rendered = output.getvalue()
        for index in range(40):
            self.assertEqual(rendered.count(f"history-{index:02d}"), 1)
        self.assertNotIn("\x1b[H", rendered)
        self.assertNotIn("\x1b[J", rendered)
        self.assertNotIn("\x1b[2J", rendered)

    def test_activity_is_separate_from_pending_transcript(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=10, columns=60)

        display.activate()
        display.set_activity("⠋ Waiting for offline-model · 0.0s")

        self.assertEqual(display._pending_output, "")
        self.assertEqual(display._activity, "⠋ Waiting for offline-model · 0.0s")

        display.set_activity("")
        display.suspend()

        self.assertEqual(display._activity, "")

    def test_assistant_preview_is_replaced_and_stable_output_commits_once(self) -> None:
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=10, columns=60)
        display.activate()

        display.update_assistant("", "🪰 **partial")
        self.assertEqual(display._assistant_preview, "🪰 **partial")
        self.assertEqual(display._pending_output, "")

        display.update_assistant("🪰 rendered answer\n", "")

        self.assertEqual(display._assistant_preview, "")
        self.assertEqual(display._pending_output, "")
        self.assertEqual(output.getvalue().count("rendered answer"), 1)
        self.assertNotIn("\x1b[H", output.getvalue())
        self.assertNotIn("\x1b[2J", output.getvalue())
        display.suspend()

    def test_resize_refresh_preserves_draft_cursor_and_committed_history(self):
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=14, columns=50)
        display.activate()
        display.write("committed-once\n")
        text = "甲乙丙丁abcdefgh\nsecond line"
        display.set_input(text, 5)
        for columns in (12, 70, 9, 50):
            display._fixed_columns = columns
            display.refresh()
            self.assertEqual(display._input, text)
            self.assertEqual(display._cursor, 5)
            self.assertEqual(display._columns, columns)
            self.assertLessEqual(display._live_rows, display._rows)
            before = output.getvalue()
            display.refresh()
            self.assertEqual(output.getvalue(), before)
        display.suspend()
        self.assertEqual(output.getvalue().count("committed-once"), 1)
        self.assertNotIn("╭", output.getvalue())
        self.assertNotIn("\x1b[2J", output.getvalue())

    def test_redirected_streams_use_plain_ansi_free_fallback(self) -> None:
        input_stream = io.StringIO("hello\n")
        output_stream = io.StringIO()

        editor = create_line_editor(input_stream, output_stream)

        self.assertIsInstance(editor, StreamLineEditor)
        self.assertEqual(editor.read_line(), "hello\n")
        self.assertEqual(output_stream.getvalue(), "you> ")
        self.assertNotIn("\x1b", output_stream.getvalue())

    def test_stream_editor_reports_eof_without_fabricating_a_line(self) -> None:
        output_stream = io.StringIO()
        editor = StreamLineEditor(io.StringIO(""), output_stream)

        self.assertIsNone(editor.read_line())
        self.assertEqual(output_stream.getvalue(), "you> ")

    def test_frame_stays_inside_the_terminal_last_column(self) -> None:
        top, bottom = ReadlineLineEditor._frame_lines(80)

        self.assertEqual(len(top), 79)
        self.assertEqual(len(bottom), 79)
        self.assertTrue(top.startswith("╭─ prompt "))
        self.assertTrue(top.endswith("╮"))
        self.assertTrue(bottom.startswith("╰"))
        self.assertTrue(bottom.endswith("╯"))

    def test_form_labels_restore_normal_input_even_after_interruption(self) -> None:
        for framed in (True, False):
            output = io.StringIO()
            prompts = []
            def interrupt(prompt):
                prompts.append(prompt)
                raise KeyboardInterrupt
            editor = ReadlineLineEditor(output, reader=interrupt, framed=framed)
            with self.assertRaises(KeyboardInterrupt):
                read_field_line(editor, "Model label")
            self.assertIn("Model label", output.getvalue() if framed else prompts[0])
            self.assertEqual(editor.frame_label, "prompt")
        output = io.StringIO()
        editor = StreamLineEditor(io.StringIO("name\nnext\n"), output)
        self.assertEqual(read_field_line(editor, "Model label"), "name\n")
        self.assertEqual(editor.read_line(), "next\n")
        self.assertEqual(output.getvalue(), "Model label> you> ")

    def test_keyboard_interrupt_restores_a_bottom_border(self) -> None:
        output_stream = io.StringIO()

        def interrupt(_prompt: str) -> str:
            raise KeyboardInterrupt

        editor = ReadlineLineEditor(output_stream, reader=interrupt, framed=True)

        with self.assertRaises(KeyboardInterrupt):
            editor.read_line()

        self.assertTrue(output_stream.getvalue().endswith("╯\n"))

    def test_unframed_readline_path_emits_no_application_ansi(self) -> None:
        output_stream = io.StringIO()

        def read(prompt: str) -> str:
            output_stream.write(prompt)
            return "hello"

        editor = ReadlineLineEditor(output_stream, reader=read, framed=False)

        self.assertEqual(editor.read_line(), "hello")
        self.assertEqual(output_stream.getvalue(), "❯ ")
        self.assertNotIn("\x1b", output_stream.getvalue())


@unittest.skipUnless(os.name == "posix", "PTY regression requires a POSIX terminal")
class TerminalInputPtyRegressionTest(unittest.TestCase):
    def test_improvement_field_echoes_before_submission_and_restores_menu_input(self):
        import fcntl
        import struct
        import termios
        code = (
            "import asyncio, sys, termios\n"
            "from fruitfly_agent.interactive import TerminalFrontend\n"
            "from fruitfly_agent.interactive.terminal.bindings import ImprovementClients\n"
            "from tests.support.application import offline_session\n"
            "frontend=TerminalFrontend(offline_session(), improvement_clients=ImprovementClients(search=object()))\n"
            "with frontend.menu_scope():\n"
            "    value=asyncio.run(frontend.improvement_frontend().read_value('Search guidance\\nCurrent: old value'))\n"
            "    print('MENU_ACTIVE='+str(frontend.line_editor.display.active),flush=True)\n"
            "frontend._suspend_inline_terminal()\n"
            "print('ECHO='+str(bool(termios.tcgetattr(sys.stdin.fileno())[3] & termios.ECHO)),flush=True)\n"
            "print('RESULT='+repr(value),flush=True)\n"
        )
        pid, master = pty.fork()
        if pid == 0:
            os.chdir(ROOT)
            os.environ['TERM'] = 'xterm-256color'
            os.execl(sys.executable, sys.executable, '-c', code)
        chunks = []
        try:
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
            self._read_until(master, '❯ '.encode(), chunks)
            os.write(master, 'Ｈello'.encode())
            # No Enter has been sent: the draft itself must be rendered.
            self._read_until(master, '❯ Ｈello'.encode(), chunks)
            os.write(master, b'\x1b[D!\r')
            self._read_until_exit(pid, master, chunks)
            self._drain(master, chunks)
        except BaseException:
            self._kill_and_reap(pid)
            raise
        finally:
            os.close(master)
        output = b''.join(chunks).decode(errors='replace')
        self.assertIn('Current: old value', output)
        self.assertIn("RESULT='Ｈell!o'", output)
        self.assertIn('MENU_ACTIVE=False', output)
        self.assertIn('ECHO=True', output)

    def test_suspended_form_restores_display_history_and_echo_on_every_exit(self):
        for keys, result in ((b'value\r', "'value'"), (b'q 1\r', "'q 1'"),
                             (b'\x04', 'None'), (b'\x03', "'cancelled'"), (b'\x1b', "'cancelled'")):
            with self.subTest(keys=keys):
                code = (
                    "import sys, termios\n"
                    "from fruitfly_agent.interactive.terminal.io.live import InlineTerminalDisplay, IsolatedLineEditor, InputInterrupted\n"
                    "from fruitfly_agent.interactive.terminal.io.input import read_field_line\n"
                    "display=InlineTerminalDisplay(sys.stdout); editor=IsolatedLineEditor(sys.stdin,display)\n"
                    "editor._history=['chat entry']\n"
                    "try:\n"
                    "    value=read_field_line(editor,'Variable')\n"
                    "except InputInterrupted:\n"
                    "    value='cancelled'\n"
                    "print('RESTORED='+str(editor.display is display and not display.active and editor._history==['chat entry']),flush=True)\n"
                    "print('ECHO='+str(bool(termios.tcgetattr(sys.stdin.fileno())[3] & termios.ECHO)),flush=True)\n"
                    "print('RESULT='+repr(value),flush=True)\n"
                )
                output = self._run_pty_code(code, keys)
                self.assertIn('RESTORED=True', output)
                self.assertIn('ECHO=True', output)
                self.assertIn('RESULT=' + result, output)

    def test_idle_resize_rewraps_draft_without_keys_and_preserves_editing(self):
        import fcntl
        import struct
        import termios
        code = (
            "import sys; from fruitfly_agent.interactive.terminal.io.live import InlineTerminalDisplay, IsolatedLineEditor; "
            "display=InlineTerminalDisplay(sys.stdout); editor=IsolatedLineEditor(sys.stdin,display); "
            "display.activate(); display.write('committed-once\\n'); value=editor.read_line(); "
            "display.suspend(); editor.stop(); print('RESULT='+repr(value),flush=True)"
        )
        pid, master = pty.fork()
        if pid == 0:
            os.chdir(ROOT)
            os.environ["TERM"] = "xterm-256color"
            os.environ.pop("NO_COLOR", None)
            os.environ["COLORFGBG"] = "15;0"
            os.execl(sys.executable, sys.executable, "-c", code)
        chunks = []
        try:
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 20, 60, 0, 0))
            self._read_until(master, "❯ ".encode(), chunks)
            os.write(master, "甲乙丙丁abcdefgh".encode())
            self._read_until(master, "❯ 甲乙丙丁abcdefgh".encode(), chunks)
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 20, 12, 0, 0))
            narrow = []
            self._read_until(master, "│ abcdefgh".encode(), narrow)
            chunks.extend(narrow)
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 20, 50, 0, 0))
            wide = []
            self._read_until(master, "❯ 甲乙丙丁abcdefgh".encode(), wide)
            chunks.extend(wide)
            os.write(master, b'\x1b[DX\r')
            self._read_until_exit(pid, master, chunks)
            self._drain(master, chunks)
        except BaseException:
            self._kill_and_reap(pid)
            raise
        finally:
            os.close(master)
        output = b''.join(chunks).decode(errors='replace')
        self.assertIn("RESULT='甲乙丙丁abcdefgXh'", output)
        self.assertEqual(output.count('committed-once'), 1)
        self.assertNotIn('╭', output)

    def test_isolated_control_keys_keep_text_and_cursor_consistent(self) -> None:
        for keys, value in (
            (b"one two   \x17X\r", "one X"),
            (b"abc\x01X\x05Y\r", "XabcY"),
            (b"abc\x1b[D\x04\r", "ab"),
            (b"abc\x1b[D\x15X\r", "Xc"),
        ):
            with self.subTest(keys=keys):
                self.assertIn(f"RESULT={[value]!r}", self._run_isolated_editor(keys))

    def test_isolated_history_navigation_restores_the_unsubmitted_draft(self) -> None:
        output = self._run_isolated_editor(b"first\rnew\x1b[A\x1b[B!\r", submissions=2)
        self.assertIn("RESULT=['first', 'new!']", output)

    def test_isolated_permission_selection_returns_only_the_request_reply(self) -> None:
        for keys, decision in ((b"\r", 1), (b"\x1b[B\r", 2), (b"\x1b[A\r", 3),
                               (b"\x1bOB\r", 2), (b"1", 1), (b"2", 2), (b"3", 3), (b"\x1b", 3)):
            with self.subTest(keys=keys):
                output = self._run_isolated_editor(keys, choices=("Once", "Session", "Deny"))
                expected = ["\x00authorize:request:" + str(decision)]
                self.assertIn(f"RESULT={expected!r}", output)
                self.assertIn("❯ Once", output)
                if keys in (b"\x1b[B\r", b"\x1bOB\r"):
                    self.assertIn("❯ Session", output)
                if keys == b"\x1b[A\r":
                    self.assertIn("❯ Deny", output)

    def _run_isolated_editor(self, keys: bytes, *, submissions=1, choices=()) -> str:
        code = (
            "import sys; "
            "from fruitfly_agent.interactive.terminal.io.live import IsolatedLineEditor, InlineTerminalDisplay; "
            "display=InlineTerminalDisplay(sys.stdout,rows=12,columns=50); "
            "editor=IsolatedLineEditor(sys.stdin,display); "
            f"editor.set_choices({choices!r},'request'); display.activate(); "
            f"values=[editor.read_line() for _ in range({submissions})]; "
            "display.suspend(); editor.stop(); print('RESULT='+repr(values),flush=True)"
        )
        return self._run_pty_code(code, keys)

    def test_form_frame_uses_field_name_then_restores_conversation_label(self) -> None:
        code = (
            "import sys; "
            "from fruitfly_agent.interactive.terminal.io.input import create_line_editor, read_field_line; "
            "editor=create_line_editor(sys.stdin,sys.stdout); "
            "first=read_field_line(editor,'Model label'); second=editor.read_line(); "
            "print('RESULT='+repr((first,second)),flush=True)"
        )
        output = self._run_pty_code(code, b"work-model\rnext\r", prompt=b"Model label> ")
        self.assertIn("Model label> ", output)
        self.assertIn("❯ ", output)
        self.assertNotIn("╭", output)
        self.assertIn("RESULT=('work-model', 'next')", output)

    def test_model_key_input_hides_value_and_restores_echo(self) -> None:
        code = (
            "import sys, termios; "
            "from fruitfly_agent.interactive.terminal.features.configuration.model_setup import read_secret; "
            "value=read_secret(sys.stdin, sys.stdout); "
            "print('RESULT='+str(value=='offline-placeholder'),flush=True); "
            "print('ECHO='+str(bool(termios.tcgetattr(sys.stdin)[3]&termios.ECHO)),flush=True)"
        )
        output = self._run_pty_code(code, b"offline-placeholder\r", prompt=b"API key (hidden;")
        self.assertIn("RESULT=True", output)
        self.assertIn("ECHO=True", output)
        self.assertNotIn("offline-placeholder", output)

    def test_bracketed_multiline_paste_is_one_submission(self) -> None:
        code = (
            "from fruitfly_agent.interactive.terminal.io.live import "
            "IsolatedLineEditor, InlineTerminalDisplay; "
            "import sys; "
            "display = InlineTerminalDisplay(sys.stdout, rows=12, columns=50); "
            "editor = IsolatedLineEditor(sys.stdin, display); "
            "editor.start(); display.activate(); "
            "value = editor.read_line(); "
            "display.suspend(); editor.stop(); "
            "print('RESULT=' + repr(value), flush=True)"
        )
        pasted = "Ｉｎ\tＯｕ\nＩＤ\tＡｍｔ\nＴｏｔａｌ\t97"
        keys = (
            b"\x1b[200~"
            + pasted.replace("\n", "\r\n").encode()
            + b"\x1b[201~\r"
        )

        output = self._run_pty_code(code, keys)

        self.assertIn(f"RESULT={pasted!r}", output)

    def test_up_arrow_recalls_the_previous_submission(self) -> None:
        code = (
            "from fruitfly_agent.interactive.terminal.io.live import "
            "IsolatedLineEditor, InlineTerminalDisplay; "
            "import sys; "
            "display = InlineTerminalDisplay(sys.stdout, rows=12, columns=50); "
            "editor = IsolatedLineEditor(sys.stdin, display); "
            "editor.start(); display.activate(); "
            "first = editor.read_line(); second = editor.read_line(); "
            "display.suspend(); editor.stop(); "
            "print('RESULT=' + repr((first, second)), flush=True)"
        )
        output = self._run_pty_code(code, b"first prompt\r\x1b[A\r")

        self.assertIn("RESULT=('first prompt', 'first prompt')", output)

    def test_isolated_editor_preserves_buffer_during_stream_output(self) -> None:
        code = (
            "from fruitfly_agent.interactive.terminal.io.live import "
            "IsolatedLineEditor, InlineTerminalDisplay; "
            "import sys, threading, time; "
            "display = InlineTerminalDisplay(sys.stdout, rows=12, columns=50); "
            "editor = IsolatedLineEditor(sys.stdin, display); "
            "display.activate(); "
            "worker = threading.Thread(target=lambda: "
            "(time.sleep(0.15), display.write('assistant> streamed\\n'))); "
            "worker.start(); "
            "value = editor.read_line(); "
            "worker.join(); "
            "display.suspend(); "
            "print('RESULT=' + repr(value), flush=True)"
        )
        child_pid, master_fd = pty.fork()
        if child_pid == 0:
            os.chdir(ROOT)
            os.environ["TERM"] = "xterm-256color"
            os.execl(sys.executable, sys.executable, "-c", code)
        chunks: list[bytes] = []
        try:
            self._read_until(master_fd, "❯ ".encode(), chunks)
            os.write(master_fd, "Ｗabc".encode())
            self._read_until(master_fd, b"assistant> streamed", chunks)
            os.write(master_fd, b"\x1b[DX\r")
            self._read_until_exit(child_pid, master_fd, chunks)
            self._drain(master_fd, chunks)
        except BaseException:
            self._kill_and_reap(child_pid)
            raise
        finally:
            os.close(master_fd)
        output = b"".join(chunks).decode(errors="replace")
        self.assertIn("assistant> streamed", output)
        self.assertIn("RESULT='ＷabXc'", output)

    def test_enhanced_editor_is_independent_of_parent_terminal_type(self) -> None:
        with patch.dict(os.environ, {"TERM": "dumb"}):
            output = self._run_editor(b"abc\x7f\r")
        self.assertIn("RESULT='ab'", output)
        self.assertNotIn("╰", output)

    def test_backspace_edits_the_buffer_instead_of_only_the_display(self) -> None:
        output = self._run_editor(b"abc\x7f\r")

        self.assertIn("RESULT='ab'", output)

    def test_left_arrow_moves_the_cursor_without_entering_escape_bytes(self) -> None:
        output = self._run_editor(b"abc\x1b[DX\r")

        self.assertIn("RESULT='abXc'", output)
        self.assertNotIn("RESULT='abc\\x1b", output)

    def test_navigation_and_delete_keys_edit_at_the_cursor(self) -> None:
        keys = b"abc\x1b[D\x1b[D\x1b[C\x1b[3~\x1b[HX\x1b[FY\r"

        output = self._run_editor(keys)

        self.assertIn("RESULT='XabY'", output)

    def test_ctrl_d_reports_eof_and_restores_the_frame(self) -> None:
        output = self._run_editor(b"\x04")

        self.assertIn("RESULT=None", output)
        self.assertNotIn("╰", output)

    def test_unicode_input_is_preserved(self) -> None:
        output = self._run_editor("Ｈｉ🙂\r".encode())

        self.assertIn("RESULT='Ｈｉ🙂'", output)

    def _run_editor(self, keys: bytes) -> str:
        code = (
            "from fruitfly_agent.interactive.terminal.io.input "
            "import create_line_editor; "
            "import sys; "
            "value = create_line_editor(sys.stdin, sys.stdout).read_line(); "
            "print('RESULT=' + repr(value), flush=True)"
        )
        return self._run_pty_code(code, keys)

    def _run_pty_code(self, code: str, keys: bytes, *, prompt=b"\xe2\x9d\xaf ") -> str:
        child_pid, master_fd = pty.fork()
        if child_pid == 0:
            os.chdir(ROOT)
            os.environ["INPUTRC"] = os.devnull
            os.environ["TERM"] = "xterm-256color"
            os.execl(sys.executable, sys.executable, "-c", code)
        chunks: list[bytes] = []
        try:
            self._read_until(master_fd, prompt, chunks)
            os.write(master_fd, keys)
            self._read_until_exit(child_pid, master_fd, chunks)
            self._drain(master_fd, chunks)
        except BaseException:
            self._kill_and_reap(child_pid)
            raise
        finally:
            os.close(master_fd)
        return b"".join(chunks).decode(errors="replace")

    def _read_until(
        self,
        fd: int,
        marker: bytes,
        chunks: list[bytes],
    ) -> None:
        deadline = time.monotonic() + 5
        while marker not in re.sub(rb"\x1b\[[0-9;]*m", b"", b"".join(chunks)):
            if time.monotonic() >= deadline:
                self.fail(f"terminal prompt did not appear: {b''.join(chunks)!r}")
            readable, _, _ = select.select([fd], [], [], 0.1)
            if readable:
                data = os.read(fd, 4096)
                if not data:
                    self.fail(f"terminal closed before prompt: {b''.join(chunks)!r}")
                chunks.append(data)

    @staticmethod
    def _drain(fd: int, chunks: list[bytes]) -> None:
        while True:
            readable, _, _ = select.select([fd], [], [], 0.05)
            if not readable:
                return
            try:
                data = os.read(fd, 4096)
                if not data:
                    return
                chunks.append(data)
            except OSError as exc:
                if exc.errno == errno.EIO:
                    return
                raise

    def _read_until_exit(
        self,
        child_pid: int,
        fd: int,
        chunks: list[bytes],
    ) -> None:
        deadline = time.monotonic() + 5
        while True:
            finished_pid, _ = os.waitpid(child_pid, os.WNOHANG)
            if finished_pid == child_pid:
                return
            if time.monotonic() >= deadline:
                self.fail(f"terminal input did not finish: {b''.join(chunks)!r}")
            readable, _, _ = select.select([fd], [], [], 0.1)
            if readable:
                try:
                    data = os.read(fd, 4096)
                    if data:
                        chunks.append(data)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise

    @staticmethod
    def _kill_and_reap(child_pid: int) -> None:
        try:
            os.kill(child_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            os.waitpid(child_pid, 0)
        except ChildProcessError:
            pass


if __name__ == "__main__":
    unittest.main()
