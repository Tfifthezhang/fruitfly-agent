"""TTY editing regressions for the lightweight interactive frontend."""

from __future__ import annotations

import errno
import io
import os
import pty
import select
import signal
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fruitfly_agent.interactive.terminal.input import (
    ReadlineLineEditor,
    StreamLineEditor,
    create_line_editor,
)
from fruitfly_agent.interactive.terminal.live import InlineTerminalDisplay


ROOT = Path(__file__).resolve().parents[2]


class LineEditorUnitTest(unittest.TestCase):
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
            "assistant> streamed\r\n\x1b[0m\x1b[2K╭─ prompt",
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
        self.assertIn("\x1b[2K│ ＩＤ    Ｑｔ\r\n", rendered)
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

    def test_keyboard_interrupt_restores_a_bottom_border(self) -> None:
        output_stream = io.StringIO()

        def interrupt(_prompt: str) -> str:
            raise KeyboardInterrupt

        editor = ReadlineLineEditor(output_stream, reader=interrupt)

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
        self.assertEqual(output_stream.getvalue(), "you> ")
        self.assertNotIn("\x1b", output_stream.getvalue())


@unittest.skipUnless(os.name == "posix", "PTY regression requires a POSIX terminal")
class TerminalInputPtyRegressionTest(unittest.TestCase):
    def test_bracketed_multiline_paste_is_one_submission(self) -> None:
        code = (
            "from fruitfly_agent.interactive.terminal.live import "
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
            "from fruitfly_agent.interactive.terminal.live import "
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
            "from fruitfly_agent.interactive.terminal.live import "
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
        self.assertIn("╰", output)

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
        self.assertIn("╰", output)

    def test_unicode_input_is_preserved(self) -> None:
        output = self._run_editor("Ｈｉ🙂\r".encode())

        self.assertIn("RESULT='Ｈｉ🙂'", output)

    def _run_editor(self, keys: bytes) -> str:
        code = (
            "from fruitfly_agent.interactive.terminal.input "
            "import create_line_editor; "
            "import sys; "
            "value = create_line_editor(sys.stdin, sys.stdout).read_line(); "
            "print('RESULT=' + repr(value), flush=True)"
        )
        return self._run_pty_code(code, keys)

    def _run_pty_code(self, code: str, keys: bytes) -> str:
        child_pid, master_fd = pty.fork()
        if child_pid == 0:
            os.chdir(ROOT)
            os.environ["INPUTRC"] = os.devnull
            os.environ["TERM"] = "xterm-256color"
            os.execl(sys.executable, sys.executable, "-c", code)
        chunks: list[bytes] = []
        try:
            self._read_until(master_fd, b"\xe2\x9d\xaf ", chunks)
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
        while marker not in b"".join(chunks):
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
