"""Defaults and role overrides are local, strict and Provider-free."""
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

from fruitfly_agent.experiments.configuration import load_configuration
from fruitfly_agent.experiments.composition import prepare_experiment
from fruitfly_agent.experiments.cli import main
from tests.support.experiments import workspace


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = workspace(self.root)

    def test_defaults_are_complete_and_check_constructs_no_provider(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider constructed')):
            prepared = prepare_experiment(load_configuration(self.root), 'improvement')
        self.assertEqual(prepared.request.strategy_id, 'simple')
        self.assertEqual(prepared.request.component_ids, ('base_prompt',))
        self.assertFalse(prepared.request.retain_experience)
        self.assertEqual(prepared.model_roles, dict.fromkeys(('executor', 'editor', 'assessor'), 'executor'))
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertNotIn('offline-placeholder', json.dumps(prepared.summary()))

    def test_role_overrides_do_not_modify_source_and_use_one_catalog(self):
        self.path = workspace(self.root, models={'editor': 'editor', 'assessor': 'assessor'})
        original = (self.root / '.fruitfly/default-config.yaml').read_bytes()
        prepared = prepare_experiment(load_configuration(self.root), 'improvement')
        self.assertEqual(prepared.model_roles, {'executor': 'executor', 'editor': 'editor', 'assessor': 'assessor'})
        self.assertEqual((self.root / '.fruitfly/default-config.yaml').read_bytes(), original)
        selected = next(m for m in prepared.profile.mechanisms if m.mechanism_id == 'component-improvement')
        self.assertEqual(selected.parameters, {'editor_profile': 'editor', 'assessor_profile': 'assessor'})

    def test_unknown_duplicate_and_invalid_fields_fail_without_fallback(self):
        for text in ('schema_version: 1\nunknown: true\n', 'schema_version: 1\nschema_version: 1\n',
                     'schema_version: 1\nimprovement:\n  max_model_calls: true\n',
                     'schema_version: 1\nimprovement:\n  strategy: simple\n  width: 2\n',
                     'schema_version: 1\nmodels:\n  assessor: false\n'):
            with self.subTest(text=text):
                self.path.write_text(text)
                with self.assertRaises(ValueError):
                    load_configuration(self.root)

    def test_paths_are_relative_to_the_declaring_file_and_cli_overrides_win(self):
        source = self.root / 'source.txt'
        source.write_text('Explicit source')
        workspace(self.root, task={'source': 'files', 'instruction': 'Read the source', 'input_paths': ['../source.txt']})
        config = load_configuration(self.root, overrides={'improvement': {'rounds': 2}})
        prepared = prepare_experiment(config, 'improvement')
        self.assertEqual(prepared.request.input_paths, ('source.txt',))
        self.assertEqual(prepared.request.depth, 2)
        self.assertEqual(config.sources['improvement.rounds'], 'command line')

    def test_missing_explicit_file_and_model_are_actionable(self):
        with self.assertRaisesRegex(ValueError, 'not found'):
            load_configuration(self.root, 'missing.yaml')
        workspace(self.root, models={'editor': 'unknown'})
        with self.assertRaisesRegex(ValueError, 'unknown model'):
            prepare_experiment(load_configuration(self.root), 'improvement')

    def test_independent_adoption_requires_material_before_model_construction(self):
        with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider constructed')):
            with self.assertRaisesRegex(ValueError, 'independent holdout'):
                prepare_experiment(load_configuration(self.root), 'rsi')

    def test_cli_check_json_and_report_do_not_load_models_or_run_tasks(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(['improvement', 'check', '--cwd', str(self.root), '--json']), 0)
        self.assertEqual(json.loads(output.getvalue())['model_roles']['executor'], 'executor')
        from fruitfly_agent.experiments.records import RunRecords
        records = RunRecords(self.root)
        record = records.create('improvement', {})
        self.path.unlink()
        (self.root / '.fruitfly/default-config.yaml').unlink()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--cwd', str(self.root), 'improvement', 'report', record['id']]), 0)

    def test_metadata_change_invalidates_frozen_source(self):
        prepared = prepare_experiment(load_configuration(self.root), 'improvement')
        prepared.model_path.write_text(prepared.model_path.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'changed'):
            prepared.verify_sources()

    def test_symlink_input_is_not_hidden_by_path_resolution(self):
        source = self.root / 'source.txt'
        source.write_text('Material')
        (self.root / 'link.txt').symlink_to(source)
        workspace(self.root, task={'source': 'files', 'instruction': 'Read material', 'input_paths': ['../link.txt']})
        with self.assertRaisesRegex(ValueError, 'symlink'):
            prepare_experiment(load_configuration(self.root), 'improvement')
