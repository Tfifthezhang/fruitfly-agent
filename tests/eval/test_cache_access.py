"""Cache admission changes only owned roots, preserving private runtime material."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
from fruitfly_eval.harbor import cache_access


class CacheAccessTests(unittest.TestCase):
    def test_grants_only_cache_roots_and_rejects_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'cache'; root.mkdir()
            with patch.object(cache_access, 'ROOT', root), patch.object(os, 'fchown') as chown:
                cache_access.grant(os.getgid())
                self.assertEqual(chown.call_count, 4)
                for path in (root, *(root / n for n in ('uv', 'python', 'pip'))):
                    self.assertEqual(path.stat().st_mode & 0o777, 0o770)
                (root / 'uv').rmdir()
                outside = Path(directory) / 'outside'; outside.mkdir()
                (root / 'uv').symlink_to(outside)
                with self.assertRaises(OSError):
                    cache_access.grant(os.getgid())
                self.assertNotEqual(outside.stat().st_mode & 0o7777, 0o2770)
