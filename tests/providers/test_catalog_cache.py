"""Directory cache behavior without authentication or network access."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fruitfly_agent.providers.connections.catalog import CatalogCache, CatalogScope, CatalogSnapshot


class CatalogCacheTests(unittest.TestCase):
    def test_account_isolation_staleness_and_failed_refresh_preserve_directory(self):
        with TemporaryDirectory() as directory:
            cache = CatalogCache(Path(directory))
            scope = CatalogScope('fixture', 'https://fixture.invalid', 'account-a')
            snapshot = CatalogSnapshot(({'id': 'model-a', 'context_window': 8192},), 100, 'revision-a')
            cache.write(scope, snapshot, complete=True)
            self.assertEqual(cache.read(scope), snapshot)
            self.assertIsNone(cache.read(CatalogScope('fixture', scope.endpoint, 'account-b')))
            self.assertFalse(snapshot.stale(101))
            self.assertTrue(snapshot.stale(100 + 86400))
            with self.assertRaises(ValueError):
                cache.write(scope, CatalogSnapshot((), 200), complete=False)
            with self.assertRaises(ValueError):
                cache.write(scope, CatalogSnapshot(({'id': ''},), 200), complete=True)
            self.assertEqual(cache.read(scope), snapshot)
            (Path(directory) / (scope.key() + '.json')).write_text('{broken')
            self.assertIsNone(cache.read(scope))
