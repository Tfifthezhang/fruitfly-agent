"""Image selections are structured draft items, never inferred from marker text."""
import unittest
from fruitfly_agent.interactive.terminal.features.composer import Composer
from fruitfly_agent.core.data_model import TextBlock
from tests.support.media import image
from tests.support.terminal_process import TerminalProcess


class ComposerTests(unittest.TestCase):
    def test_explicit_paths_and_paste_preserve_position_without_attaching_prose(self):
        paths = []
        def load(path):
            paths.append(path)
            return image()
        draft = Composer(load)
        text, cursor = draft.transform('Compare @"first file.png" and @second.png', 40)
        self.assertEqual(paths, ['second.png', 'first file.png'])
        self.assertEqual([type(b).__name__ for b in draft.prepare(text)],
                         ['TextBlock', 'ImageBlock', 'TextBlock', 'ImageBlock'])
        draft.clear()
        for text in ('Discuss file.png', '```\n@file.png\n```', '[Image #1]'):
            with self.subTest(text=text):
                self.assertEqual(draft.prepare(text), text)
                self.assertEqual(draft.items, [])
        draft.clear()
        text, cursor = draft.paste('Look: ', 6, '"/tmp/first file.png" /tmp/second.png')
        self.assertEqual(len(draft.items), 2)
        self.assertEqual(cursor, len(text))
        self.assertEqual(draft.prepare(text)[0], TextBlock('Look: '))

    def test_editing_and_clipboard_failure_do_not_reconstruct_forged_selections(self):
        draft = Composer(lambda _: image(), lambda: image())
        text, end = draft.paste_image('before after', 7)
        self.assertEqual(len(draft.items), 1)
        draft.update('X' + text)
        self.assertEqual(draft.items[0].start, 8)
        item = draft.items[0]
        draft.update(draft.text[:item.start] + draft.text[item.end:])
        self.assertEqual(draft.items, [])
        self.assertEqual(draft.prepare('[Image #1]'), '[Image #1]')
        draft.clear()
        draft.clipboard = lambda: None
        self.assertEqual(draft.paste_image('', 0), ('', 0))
        self.assertIn('No clipboard image', draft.notice)

    def test_live_editor_clipboard_atomic_delete_and_plain_submit(self):
        code = '''
import sys
from fruitfly_agent.interactive.terminal.io.live import create_inline_terminal
from fruitfly_agent.interactive.terminal.features.composer import Composer
from tests.support.media import image
pair = create_inline_terminal(sys.stdin, sys.stdout)
display, editor = pair
composer = Composer(lambda _: image(), lambda: image())
editor.set_input_adapter(composer)
try:
    display.activate()
    print('READY', flush=True)
    value = editor.read_line()
    print('RESULT=' + repr(composer.prepare(value)), flush=True)
finally:
    display.suspend()
'''
        with TerminalProcess(code) as terminal:
            terminal.read_until('READY')
            terminal.send(b'\x16')
            terminal.read_until('[Image #1]')
            terminal.send(b'\x7fplain\r')
            terminal.read_until("RESULT='plain'")
            terminal.finish()
