"""Component files use the ordinary runtime and preserve explicit ownership."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import yaml

from fruitfly_agent.core.session import Session
from fruitfly_agent.lab.catalog import builtin_catalog, load_system_config, materialize_system
from fruitfly_agent.run import build_runtime
from fruitfly_agent.runtime_spec import load_harness_config
from tests.support.faux_provider import FauxProvider
from tests.support.run import _write_catalog


class ComponentConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        _write_catalog(self.root / 'models.yaml', {'offline': 'offline-model'})
        self.path = self.root / 'config.yaml'
        self.document = {'id': 'execution-policy', 'role': 'H',
                         'implementation': 'execution-policy', 'parameters': {'settings': {'max_tool_calls_per_turn': 128}}}
        self.config = {'default_profile': 'baseline', 'profiles': {'baseline': {
            'models': {'catalog': 'models.yaml', 'roles': {'executor': 'offline'}},
            'H': {'execution-policy': {'file': 'execution.yaml'}, 'base_prompt': {'inline': {
                'id': 'base_prompt', 'role': 'H', 'implementation': 'base_prompt',
                'parameters': {'instructions': {'system': 'Use the supplied evidence.\nKeep exact text.\n'}}}}},
            'I': {'improvement-editor': {'inline': {'id': 'improvement-editor',
                'role': 'I', 'implementation': 'improvement-editor', 'parameters': {}}}}}}}

    def write(self):
        self.path.write_text(yaml.safe_dump(self.config))
        (self.root / 'execution.yaml').write_text(yaml.safe_dump(self.document))

    def test_parse_is_pure_and_shared_runtime_uses_exact_prompt_and_limit(self):
        _write_catalog(self.root / 'models.yaml', {'offline': 'offline-model',
            'edit': 'editor-model', 'judge': 'assessor-model'})
        self.config['profiles']['baseline']['models']['roles'].update(editor='edit', assessor='judge')
        self.write()
        raw = load_harness_config(self.path).select()
        self.assertFalse(raw.configured)
        profile = load_system_config(self.path).select()
        registry = Mock(); registry.create.return_value = FauxProvider()
        with Session(self.root / 'session.jsonl') as session:
            runtime = build_runtime(profile, config_path=self.path, catalog=builtin_catalog(),
                environment={}, session=session, cwd=self.root, provider_registry=registry)
        self.assertEqual(runtime.config.max_tool_calls_per_turn, 128)
        self.assertEqual(runtime.config.system_prompt, 'Use the supplied evidence.\nKeep exact text.\n')
        self.assertEqual(runtime.manifest.execution['max_tool_calls_per_turn'], 128)
        self.assertEqual(registry.create.call_count, 1, 'unused I must not create auxiliary clients')

    def test_candidate_bundle_reloads_without_original_component_files(self):
        self.write()
        profile = load_system_config(self.path).select()
        candidate = replace(profile, execution={'max_tool_calls_per_turn': 192})
        target = self.root / 'candidate' / 'config.yaml'
        materialize_system(candidate, target, model_source=self.root / 'models.yaml')
        (self.root / 'execution.yaml').unlink()
        reloaded = load_system_config(target).select()
        self.assertEqual(reloaded.execution['max_tool_calls_per_turn'], 192)
        self.assertEqual(reloaded.artifact_contents[reloaded.prompt], 'Use the supplied evidence.\nKeep exact text.\n')
        self.assertEqual(self.config, yaml.safe_load(self.path.read_text()))

    def test_export_copies_owner_registered_state_and_verifies_artifact_contents(self):
        from fruitfly_agent.lab.catalog import configuration_resources
        self.config['profiles']['baseline']['H']['knowledge-files'] = {'inline': {
            'id': 'knowledge-files', 'role': 'H', 'implementation': 'knowledge-files',
            'parameters': {'root': 'notes'}}}
        self.config['profiles']['baseline']['H']['information-context'] = {'inline': {
            'id': 'information-context', 'role': 'H',
            'implementation': 'information-context', 'parameters': {}}}
        self.write()
        (self.root / 'notes').mkdir()
        (self.root / 'notes' / 'guide.md').write_text('Exact registered knowledge.\n')
        (self.root / 'unrelated.txt').write_text('Private unrelated data.')
        catalog = builtin_catalog()
        profile = load_system_config(self.path).select()
        resources = configuration_resources(profile, catalog, self.root)
        target = self.root / 'export' / 'config.yaml'
        materialize_system(profile, target, model_source=self.root / 'models.yaml', resources=resources)
        self.assertEqual((target.parent / 'resources/notes/guide.md').read_text(), 'Exact registered knowledge.\n')
        self.assertFalse((target.parent / 'resources/unrelated.txt').exists())
        invalid = replace(profile, artifact_contents={profile.prompt: 'tampered'})
        with self.assertRaisesRegex(ValueError, 'content differs'):
            materialize_system(invalid, self.root / 'invalid/config.yaml')

    def test_file_and_inline_have_equal_effective_values_and_sources_are_checked(self):
        self.write()
        file_profile = load_system_config(self.path).select()
        self.config['profiles']['baseline']['H']['execution-policy'] = {'inline': self.document}
        self.path.write_text(yaml.safe_dump(self.config))
        inline = load_system_config(self.path).select()
        self.assertEqual(file_profile.to_runtime_dict(), inline.to_runtime_dict())
        with self.assertRaisesRegex(ValueError, 'source changed'):
            file_profile.source_files[0].check()

    def test_unknown_fields_role_conflicts_and_unregistered_implementations_fail(self):
        cases = [('role', 'S'), ('implementation', 'missing'), ('parameters', {'provider': 'arbitrary'})]
        for field, value in cases:
            with self.subTest(field=field):
                original = dict(self.document)
                self.document[field] = value
                self.write()
                with self.assertRaises(ValueError):
                    load_system_config(self.path)
                self.document = original

    def test_duplicate_yaml_keys_fail_and_no_component_artifact_is_written_during_load(self):
        self.write()
        load_system_config(self.path)
        self.assertFalse((self.root / '.fruitfly').exists())
        (self.root / 'execution.yaml').write_text('id: x\nid: y\n')
        with self.assertRaisesRegex(ValueError, 'distinct'):
            load_system_config(self.path)

    def test_version_markers_flat_profiles_and_duplicate_model_bindings_are_rejected(self):
        import copy
        for location in ('system', 'component', 'flat', 'model-binding'):
            with self.subTest(location=location):
                document = copy.deepcopy(self.config)
                component = copy.deepcopy(self.document)
                if location == 'system':
                    document['schema_version'] = 2
                elif location == 'component':
                    component['schema_version'] = 1
                elif location == 'flat':
                    document['profiles']['baseline'] = {'model': {'catalog': 'models.yaml'}, 'mechanisms': []}
                else:
                    document['profiles']['baseline']['I']['component-improvement'] = {'inline': {
                        'id': 'component-improvement', 'role': 'I', 'implementation': 'component-improvement',
                        'parameters': {'editor_profile': 'offline'}}}
                self.path.write_text(yaml.safe_dump(document))
                (self.root / 'execution.yaml').write_text(yaml.safe_dump(component))
                with self.assertRaises(ValueError):
                    load_system_config(self.path)
