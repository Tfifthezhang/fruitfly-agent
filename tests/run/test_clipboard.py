"""Clipboard adapters use bounded files and never execute a shell or read stdin."""
from pathlib import Path
from types import SimpleNamespace
import subprocess
import unittest
from unittest.mock import patch

from fruitfly_agent.run.runtime.clipboard import read_clipboard_image
from tests.support.media import png_bytes, image


class ClipboardTests(unittest.TestCase):
    def test_linux_clipboard_validates_bytes_and_uses_bounded_timeout(self):
        def run(command, **kwargs):
            self.assertEqual(command[0], 'wl-paste')
            self.assertEqual(kwargs['timeout'], 3)
            self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
            kwargs['stdout'].write(png_bytes())
            return SimpleNamespace(returncode=0)
        with patch('fruitfly_agent.run.runtime.clipboard.sys.platform', 'linux'), patch(
                'fruitfly_agent.run.runtime.clipboard.shutil.which', return_value='/fixture/wl-paste'), patch(
                'fruitfly_agent.run.runtime.clipboard.subprocess.run', side_effect=run):
            self.assertEqual(read_clipboard_image(), image())

    def test_absence_timeout_and_invalid_bytes_preserve_explicit_failures(self):
        with patch('fruitfly_agent.run.runtime.clipboard.shutil.which', return_value=None):
            self.assertIsNone(read_clipboard_image())
        with patch('fruitfly_agent.run.runtime.clipboard.sys.platform', 'linux'), patch(
                'fruitfly_agent.run.runtime.clipboard.shutil.which', return_value='/fixture/wl-paste'), patch(
                'fruitfly_agent.run.runtime.clipboard.subprocess.run', side_effect=subprocess.TimeoutExpired('fixture', 3)):
            with self.assertRaisesRegex(ValueError, 'timed out'):
                read_clipboard_image()
