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
            raw['stages']['propose']['optimization'] = {'scope': 'defaults', 'include': {}, 'exclude': []}
            path.write_text(yaml.safe_dump(raw))
            with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider')):
                result = defaults(SimpleNamespace(config=str(path)), root)
            self.assertEqual(len(result['components']), 10)
            self.assertIn('subagent', result['components'])
            self.assertNotIn('file-memory', result['components'])
            self.assertNotIn('improvement-editor', result['components'])

    def document(self, root, stage='import'):
        path = root / 'experiment.yaml'
        path.write_text('# Keep this user comment\n' + yaml.safe_dump({
            'research': {'id': 'study', 'output_root': '.', 'branch': 'main'},
            'baseline': {'config': 'system.yaml'},
            'stages': {'import': {'source': 'eval', 'path': 'archive'},
                **({stage: {}} if stage != 'import' else {})},
            'next': {'stage': stage}}, sort_keys=False))
        return path

    def test_loading_and_preview_preserve_authored_bytes_and_concurrent_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.document(Path(directory))
            before = path.read_bytes()
            ResearchContext.resolve(path).preview()
            self.assertEqual(before, path.read_bytes())
            path.write_text(path.read_text() + '\n# Concurrent author edit\n')
            after = path.read_bytes()
            ResearchContext.resolve(path).preview()
            self.assertEqual(after, path.read_bytes())

    def test_removed_top_level_controls_and_next_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.document(Path(directory))
            original = yaml.safe_load(path.read_text())
            for name in ('roles', 'overrides', 'optimization', 'evidence', 'observed'):
                with self.subTest(field=name):
                    path.write_text(yaml.safe_dump({**original, name: {}}))
                    with self.assertRaises(ValueError):
                        ResearchDocument(path)
            original['next']['inputs'] = {}
            path.write_text(yaml.safe_dump(original))
            with self.assertRaises(ValueError):
                ResearchDocument(path)

    def test_stage_allowance_is_local_and_nonselected_references_are_lazy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.document(Path(directory))
            raw = yaml.safe_load(path.read_text())
            raw['stages'].update(organize={'inputs': {'batches': [{'artifact': 'future'}]},
                'allowance': {'seconds': 40, 'evidence_characters': 2000, 'evidence_responses': 4}},
                propose={'allowance': {'seconds': 80}})
            path.write_text(yaml.safe_dump(raw))
            document = ResearchDocument(path)
            self.assertEqual(ResearchContext.resolve(path).stage, 'import')
            self.assertEqual(document.experiment('organize')['evidence']['supply']['max_pages'], 4)
            self.assertEqual(document.experiment('propose')['evidence']['supply']['max_pages'], 64)
            self.assertEqual(document.experiment('propose')['execution']['editor_seconds'], 80)
            for allowance in ({'seconds': float('nan')}, {'evidence_responses': 1.5}, {'seconds': True}):
                raw['stages']['organize']['allowance'] = allowance
                path.write_text(yaml.safe_dump(raw))
                with self.assertRaises(ValueError):
                    ResearchDocument(path)

    def test_named_reference_is_scoped_to_branch_and_no_latest_is_guessed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = self.document(root, 'organize')
            raw = yaml.safe_load(path.read_text())
            raw['stages']['organize']['inputs'] = {'batches': [{'artifact': 'original'}]}
            path.write_text(yaml.safe_dump(raw))
            with self.assertRaisesRegex(ValueError, 'unknown branch artifact'):
                ResearchContext.resolve(path)
            (root / 'references.json').write_text(json.dumps({'main:original': {'bundle': 'inputs/a/bundle.json'}}))
            result = ResearchContext.resolve(path)
            self.assertEqual(result.inputs['batches'], [str((root / 'inputs/a/bundle.json').resolve())])
            with self.assertRaisesRegex(ValueError, 'differs from next.stage'):
                ResearchContext.resolve(path, 'propose')

    def test_all_stage_syntax_is_validated_without_resolving_material(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.document(Path(directory))
            raw = yaml.safe_load(path.read_text())
            raw['stages']['execute'] = {'future_setting': 'not needed for import'}
            path.write_text(yaml.safe_dump(raw))
            with self.assertRaises(ValueError):
                ResearchContext.resolve(path)

    def test_import_selection_has_strict_task_and_original_identity_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.document(Path(directory))
            raw = yaml.safe_load(path.read_text())
            settings = raw['stages']['import']
            settings.update(task_names=['fixture'], evidence_paths={'artifacts/answer.txt': 'sha256:' + 'a' * 64})
            path.write_text(yaml.safe_dump(raw))
            self.assertEqual(ResearchDocument(path).settings('import')['task_names'], ['fixture'])
            for field, value in (('task_names', 'fixture'), ('evidence_paths', {'answer': 'bad-hash'}), ('unknown', 1)):
                with self.subTest(field=field):
                    invalid = dict(settings); invalid[field] = value
                    raw['stages']['import'] = invalid
                    path.write_text(yaml.safe_dump(raw))
                    with self.assertRaises(ValueError):
                        ResearchDocument(path).settings('import')

    def test_delegation_is_stage_local_strict_and_does_not_resolve_future_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.document(Path(directory), 'propose')
            raw = yaml.safe_load(path.read_text())
            raw['stages']['propose']['delegation'] = {'enabled': True, 'workers': ['evidence-reader']}
            raw['stages']['propose']['inputs'] = {'batches': [{'artifact': 'future-batch'}]}
            path.write_text(yaml.safe_dump(raw))
            document = ResearchDocument(path)
            self.assertTrue(document.experiment('propose')['evidence']['delegation']['enabled'])
            for delegation in ({'enabled': 'yes'}, {'enabled': True, 'workers': []},
                    {'workers': ['invalid/worker']}, {'permissions': 'unrestricted'}):
                with self.subTest(delegation=delegation):
                    raw['stages']['propose']['delegation'] = delegation
                    path.write_text(yaml.safe_dump(raw))
                    with self.assertRaises(ValueError):
                        ResearchDocument(path)
