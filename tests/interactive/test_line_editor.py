"""Line editor behavior and failure contracts."""
from __future__ import annotations
import io
import unittest
from pathlib import Path
from fruitfly_agent.interactive.terminal.io.input import ReadlineLineEditor, StreamLineEditor, create_line_editor, read_field_line

ROOT = Path(__file__).resolve().parents[2]


class LineEditorUnitTest(unittest.TestCase):
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
