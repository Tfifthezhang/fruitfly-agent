"""Editor terminal behavior and failure contracts."""
from __future__ import annotations
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.support.terminal_process import TerminalProcess, run_terminal
ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == 'posix', 'PTY regression requires a POSIX terminal')
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
        with TerminalProcess(code, rows=24, columns=80) as terminal:
            terminal.read_until('❯ ')
            terminal.send('Ｈello'.encode())
            # The draft is visible before Enter.
            terminal.read_until('❯ Ｈello')
            terminal.send(b'\x1b[D!\r')
            output = terminal.finish()
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
                output = run_terminal(code, keys)
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
        with TerminalProcess(code, rows=20, columns=60,
                environment={'NO_COLOR': None, 'COLORFGBG': '15;0'}) as terminal:
            terminal.read_until('❯ ')
            terminal.send('ＷＸＹＺabcdefgh'.encode())
            terminal.read_until('❯ ＷＸＹＺabcdefgh')
            start = len(terminal.output)
            terminal.resize(20, 12)
            terminal.read_until('│ abcdefgh', start=start)
            start = len(terminal.output)
            terminal.resize(20, 50)
            terminal.read_until('❯ ＷＸＹＺabcdefgh', start=start)
            terminal.send(b'\x1b[DX\r')
            output = terminal.finish()
        self.assertIn("RESULT='ＷＸＹＺabcdefgXh'", output)
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
        return run_terminal(code, keys)

    def test_form_frame_uses_field_name_then_restores_conversation_label(self) -> None:
        code = (
            "import sys; "
            "from fruitfly_agent.interactive.terminal.io.input import create_line_editor, read_field_line; "
            "editor=create_line_editor(sys.stdin,sys.stdout); "
            "first=read_field_line(editor,'Model label'); second=editor.read_line(); "
            "print('RESULT='+repr((first,second)),flush=True)"
        )
        output = run_terminal(code, b"work-model\rnext\r", prompt=b"Model label> ")
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
        output = run_terminal(code, b"offline-placeholder\r", prompt=b"API key (hidden;")
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

        output = run_terminal(code, keys)

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
        output = run_terminal(code, b"first prompt\r\x1b[A\r")

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
        with TerminalProcess(code) as terminal:
            terminal.read_until('❯ ')
            terminal.send('Ｗabc'.encode())
            terminal.read_until('assistant> streamed')
            terminal.send(b'\x1b[DX\r')
            output = terminal.finish()
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
        return run_terminal(code, keys)
