"""Explicit namespace migration preserves source evidence and rejects conflicts."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fruitfly_agent.run.migrate_improvement import migrate_improvement


class ImprovementMigrationTests(unittest.TestCase):
    def workspace(self, root):
        old = root / '.fruitfly' / 'optimization'
        (old / 'candidates').mkdir(parents=True)
        record = {'candidate_id': 'a' * 32, 'target': 'base_prompt', 'status': 'proposed',
                  'evidence': [['Search history', '.fruitfly/optimization/searches/run.jsonl'],
                               ['Search history hash', 'unchanged-hash']]}
        (old / 'candidates' / ('a' * 32 + '.json')).write_text(json.dumps(record))
        (old / 'searches').mkdir()
        (old / 'searches/run.jsonl').write_text('{"immutable":"original bytes"}\n')
        config = root / '.fruitfly/config.yaml'
        config.write_text('''# Preserve this user comment.
schema_version: 1
default_profile: default
profiles:
  default:
    model: {catalog: models.yaml, profile: offline}
    mechanisms:
      - id: opro
        enabled: true
        parameters:
          optimizer_profile: helper # Preserve the role comment.
          cases_path: .fruitfly/optimization/cases.json
''')
        return old, config

    def test_preview_apply_and_repeat_preserve_originals_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, config = self.workspace(root)
            original_config = config.read_bytes()
            evidence = (old / 'searches/run.jsonl').read_bytes()
            preview = migrate_improvement(root)
            self.assertFalse(preview['applied'])
            self.assertEqual(config.read_bytes(), original_config)
            result = migrate_improvement(root, apply=True)
            self.assertTrue(result['applied'])
            self.assertFalse(old.exists())
            new = root / '.fruitfly/improvement'
            self.assertEqual((new / 'searches/run.jsonl').read_bytes(), evidence)
            row = json.loads(next((new / 'candidates').glob('*.json')).read_text())
            self.assertEqual((row['role'], row['status']), ('H', 'stale'))
            self.assertEqual(dict(row['evidence'])['Search history hash'], 'unchanged-hash')
            self.assertIn('improver_profile: helper # Preserve the role comment.', config.read_text())
            self.assertIn('# Preserve this user comment.', config.read_text())
            self.assertEqual((root / result['backup'] / 'config.yaml').read_bytes(), original_config)
            self.assertFalse(migrate_improvement(root, apply=True)['applied'])

    def test_conflicts_symlinks_and_unclassified_targets_leave_sources_untouched(self):
        for mode in ('conflict', 'symlink', 'unknown-role'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                old, config = self.workspace(root)
                if mode == 'conflict':
                    (root / '.fruitfly/improvement').mkdir()
                elif mode == 'symlink':
                    (old / 'link').symlink_to(config)
                else:
                    file = next((old / 'candidates').glob('*.json'))
                    row = json.loads(file.read_text())
                    row['target'] = 'unknown'
                    file.write_text(json.dumps(row))
                original = config.read_bytes()
                with self.assertRaises(ValueError):
                    migrate_improvement(root, apply=True)
                self.assertTrue(old.exists())
                self.assertEqual(config.read_bytes(), original)

    def test_failed_configuration_write_restores_data_and_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, config = self.workspace(root)
            original = config.read_bytes()
            with patch('fruitfly_agent.run.migrate_improvement.write_bytes', side_effect=OSError('write failed')):
                with self.assertRaises(OSError):
                    migrate_improvement(root, apply=True)
            self.assertTrue(old.exists())
            self.assertFalse((root / '.fruitfly/improvement').exists())
            self.assertEqual(config.read_bytes(), original)
