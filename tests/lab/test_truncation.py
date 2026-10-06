"""Tool payload limits preserve UTF-8 and the requested head or tail."""
import unittest

from fruitfly_agent.lab.tools.truncate import truncate_head, truncate_tail


class TruncationTests(unittest.TestCase):
    def test_oversized_single_line_has_a_hard_byte_limit(self):
        for content in ('x' * 80000, 'ＡＢ🪰' * 20000):
            for clip in (truncate_head, truncate_tail):
                with self.subTest(clip=clip.__name__, unicode=content[0] != 'x'):
                    result = clip(content)
                    self.assertTrue(result.truncated)
                    self.assertEqual('bytes', result.truncated_by)
                    self.assertLessEqual(result.output_bytes, 51200)
                    self.assertEqual(result.output_bytes, len(result.content.encode('utf-8')))
                    self.assertNotIn('\ufffd', result.content)
                    self.assertTrue(content.startswith(result.content) if clip is truncate_head
                                    else content.endswith(result.content))

    def test_normal_text_and_complete_line_selection_are_preserved(self):
        for clip in (truncate_head, truncate_tail):
            result = clip('a\nb\nc\n')
            self.assertEqual('a\nb\nc\n', result.content)
            self.assertFalse(result.truncated)
        self.assertEqual('abc', truncate_head('abc\ndef\nghi', max_bytes=5).content)
        self.assertEqual('ghi', truncate_tail('abc\ndef\nghi', max_bytes=5).content)
        self.assertEqual('a\nb', truncate_head('a\nb\nc', max_lines=2).content)
        self.assertEqual('b\nc', truncate_tail('a\nb\nc', max_lines=2).content)
        self.assertEqual('b\nc\n', truncate_tail('a\nb\nc\n', max_lines=2).content)

    def test_tiny_byte_limit_does_not_split_a_character(self):
        for clip in (truncate_head, truncate_tail):
            for budget in (0, 1, 2, 3):
                with self.subTest(clip=clip.__name__, budget=budget):
                    result = clip('🪰' * 10, max_bytes=budget)
                    self.assertEqual('', result.content)
                    self.assertEqual(0, result.output_bytes)

    def test_trailing_newline_does_not_hide_an_oversized_shell_line(self):
        result = truncate_tail('x' * 80000 + '\n')
        self.assertIn('x', result.content)
        self.assertTrue(result.content.endswith('\n'))
        self.assertLessEqual(result.output_bytes, 51200)

    def test_zero_line_limit_and_invalid_limits(self):
        for clip in (truncate_head, truncate_tail):
            self.assertEqual('', clip('a\nb', max_lines=0).content)
            for option in ({'max_bytes': -1}, {'max_lines': -1}, {'max_bytes': True}):
                with self.subTest(clip=clip.__name__, option=option), self.assertRaises(ValueError):
                    clip('a', **option)
