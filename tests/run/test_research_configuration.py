"""The editable document preserves intent across independent stage processes."""
import json
from pathlib import Path
import tempfile
import unittest
import yaml
from fruitfly_agent.run.improvement.configuration import ResearchDocument
from fruitfly_agent.run.improvement.context import ResearchContext


class ResearchConfigurationTests(unittest.TestCase):
    def test_default_scope_accepts_an_empty_include_map_without_a_provider(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from fruitfly_agent.experiments.operations.research import defaults
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = self.document(root, 'propose')
            raw = yaml.safe_load(path.read_text())
            raw['baseline'] = {'config': str(Path('examples/configuration/default-config.example.yaml').resolve())}
            raw['optimization'] = {'scope': 'defaults', 'include': {}, 'exclude': []}
            path.write_text(yaml.safe_dump(raw))
            with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider')):
                result = defaults(SimpleNamespace(config=str(path)), root)
            self.assertEqual(len(result['components']), 9)
            self.assertNotIn('file-memory', result['components'])
            self.assertNotIn('improvement-editor', result['components'])

    def document(self, root, stage='import'):
        path = root / 'experiment.yaml'
        path.write_text('# Keep this user comment\n' + yaml.safe_dump({
            'research': {'id': 'study', 'output_root': '.', 'branch': 'main'},
            'baseline': {'config': 'system.yaml'},
            'stages': {'import': {'source': 'eval', 'path': 'archive'}},
            'next': {'stage': stage, 'inputs': {}}}, sort_keys=False))
        return path

    def test_generated_observations_preserve_user_control_and_comments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.document(Path(directory))
            before = path.read_text()
            document = ResearchDocument(path)
            self.assertTrue(document.update_observed({'last_invocation': {'stage': 'propose'}}))
            self.assertTrue(path.read_text().startswith(before.rstrip()))
            restored = ResearchDocument(path)
            self.assertEqual(restored.next['stage'], 'import')
            restored.update_observed({'recent': []})
            self.assertEqual(path.read_text().count('observed:'), 1)

    def test_concurrent_edit_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.document(Path(directory))
            document = ResearchDocument(path)
            path.write_text(path.read_text() + '\n# User changed settings\n')
            self.assertFalse(document.update_observed({'recent': []}))
            self.assertIn('User changed settings', path.read_text())

    def test_named_reference_is_scoped_to_branch_and_no_latest_is_guessed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = self.document(root, 'organize')
            raw = yaml.safe_load(path.read_text())
            raw['next']['inputs'] = {'batches': [{'artifact': 'original'}]}
            path.write_text(yaml.safe_dump(raw))
            with self.assertRaisesRegex(ValueError, 'unknown branch artifact'):
                ResearchContext.resolve(path)
            (root / 'references.json').write_text(json.dumps({'main:original': {'bundle': 'inputs/a/bundle.json'}}))
            result = ResearchContext.resolve(path)
            self.assertEqual(result.inputs['batches'], [str((root / 'inputs/a/bundle.json').resolve())])
            with self.assertRaisesRegex(ValueError, 'differs from next.stage'):
                ResearchContext.resolve(path, 'propose')

    def test_selected_stage_validates_only_its_own_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.document(Path(directory))
            raw = yaml.safe_load(path.read_text())
            raw['stages']['execute'] = {'future_setting': 'not needed for import'}
            path.write_text(yaml.safe_dump(raw))
            self.assertEqual(ResearchContext.resolve(path).stage, 'import')
            with self.assertRaises(ValueError):
                ResearchDocument(path).settings('execute')
