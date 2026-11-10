"""Component files use the ordinary runtime and preserve explicit ownership."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import yaml

from fruitfly_agent.core.session import Session
from fruitfly_agent.lab.catalog import builtin_catalog, component_profile, load_system_config, materialize_system
from fruitfly_agent.run import build_runtime
from fruitfly_agent.runtime_spec import load_harness_config
from tests.support.faux_provider import FauxProvider
from tests.support.run import _write_catalog


class ComponentConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        _write_catalog(self.root / 'models.yaml', {'offline': 'offline-model'})
        self.path = self.root / 'config.yaml'
        self.document = {'id': 'layered-compaction', 'role': 'H',
                         'implementation': 'layered-compaction', 'parameters': {'settings': {'tail_tokens': 512}}}
        self.config = {'default_profile': 'baseline', 'profiles': {'baseline': {
            'models': {'catalog': 'models.yaml', 'roles': {'executor': 'offline'}},
            'H': {'local-env': {'default': True}, 'read-tool': {'default': True},
                  'layered-compaction': {'file': 'reduction.yaml'}, 'base_prompt': {'inline': {
                'id': 'base_prompt', 'role': 'H', 'implementation': 'base_prompt',
                'parameters': {'instructions': {'system': 'Use the supplied evidence.\nKeep exact text.\n'}}}}},
            'I': {'improvement-editor': {'inline': {'id': 'improvement-editor',
                'role': 'I', 'implementation': 'improvement-editor', 'parameters': {}}}}}}}

    def write(self):
        self.path.write_text(yaml.safe_dump(self.config))
        (self.root / 'reduction.yaml').write_text(yaml.safe_dump(self.document))

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
        self.assertEqual(next(c for c in runtime.manifest.components if c['id'] == 'layered-compaction')['parameters']['tail_tokens'], 512)
        self.assertEqual(runtime.config.system_prompt, 'Use the supplied evidence.\nKeep exact text.\n')
        self.assertEqual(runtime.manifest.execution['max_tool_calls_per_turn'], 512)
        self.assertEqual(registry.create.call_count, 1, 'unused I must not create auxiliary clients')
        self.assertEqual('editor-model', runtime.manifest.model_roles['editor']['model'])
        self.assertEqual('assessor-model', runtime.manifest.model_roles['assessor']['model'])

    def test_candidate_bundle_reloads_without_original_component_files(self):
        self.write()
        profile = load_system_config(self.path).select()
        candidate = replace(profile, mechanisms=tuple(replace(m, parameters={**m.parameters, 'tail_tokens':768}) if m.mechanism_id == 'layered-compaction' else m for m in profile.mechanisms))
        target = self.root / 'candidate' / 'config.yaml'
        materialize_system(candidate, target, model_source=self.root / 'models.yaml')
        (self.root / 'reduction.yaml').unlink()
        reloaded = load_system_config(target).select()
        self.assertEqual(next(m for m in reloaded.mechanisms if m.mechanism_id == 'layered-compaction').parameters['tail_tokens'], 768)
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
        self.config['profiles']['baseline']['H']['layered-compaction'] = {'inline': self.document}
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
        (self.root / 'reduction.yaml').write_text('id: x\nid: y\n')
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
                (self.root / 'reduction.yaml').write_text(yaml.safe_dump(component))
                with self.assertRaises(ValueError):
                    load_system_config(self.path)

    def test_inherited_memory_model_follows_executor_and_explicit_override_stays_independent(self):
        from fruitfly_agent.core.data_model import ContextItem, ContextSnapshot, UserMessage
        import asyncio
        _write_catalog(self.root / 'models.yaml', {'offline': 'original-model', 'next': 'next-model', 'small': 'memory-model'})
        self.config['profiles']['baseline']['H']['working-memory-reduction'] = {'inline': {
            'id': 'working-memory-reduction', 'role': 'H', 'implementation': 'working-memory-reduction', 'parameters': {}}}
        self.config['profiles']['baseline']['H'].pop('layered-compaction')
        for binding, expected in (({'inherit': 'executor'}, 'next-model'), ('small', 'memory-model')):
            with self.subTest(binding=binding):
                self.config['profiles']['baseline']['models']['roles']['working_memory'] = binding
                self.write()
                original = load_system_config(self.path).select()
                profile = replace(original, model_profile='next')
                provider = FauxProvider(); provider.respond_text('memory')
                registry = Mock(); registry.create.return_value = provider
                with Session(self.root / ('session-' + expected + '.jsonl')) as session:
                    runtime = build_runtime(profile, config_path=self.path, catalog=builtin_catalog(),
                        environment={}, session=session, cwd=self.root, provider_registry=registry)
                    reducer = runtime.components['working-memory-checkpoint']
                    message = UserMessage('evidence ' * 1000)
                    snapshot = ContextSnapshot((ContextItem('one', message),), (message,), '', (), 1024, 'next-model', 32, 'budget')
                    asyncio.run(reducer.check_budget(snapshot))
                    self.assertEqual(expected, provider.calls[0]['model'])
                    self.assertEqual(expected, runtime.manifest.model_roles['working_memory']['model'])
                projected = component_profile(profile, builtin_catalog())
                self.assertEqual(binding, projected.to_dict()['models']['roles']['working_memory'])

    def test_ordinary_save_externalizes_explicit_content_and_keeps_default_references(self):
        from fruitfly_agent.run.configuration.profile import save_harness_config
        self.write()
        config = load_system_config(self.path)
        expected = config.select().to_runtime_dict()
        save_harness_config(self.path, config)
        raw = yaml.safe_load(self.path.read_text())['profiles']['baseline']
        self.assertEqual(raw['H']['read-tool'], {'default': True})
        self.assertIn('file', raw['H']['base_prompt'])
        self.assertNotIn('inline', raw['I']['improvement-editor'])
        self.assertEqual(load_system_config(self.path).select().to_runtime_dict(), expected)
        self.assertEqual(raw['H']['layered-compaction'], {'file': 'reduction.yaml'})

    def test_ordinary_save_rolls_back_component_files_when_main_write_fails(self):
        from unittest.mock import patch
        from fruitfly_agent.run.configuration.profile import save_harness_config
        self.write()
        config = load_system_config(self.path)
        before = self.path.read_bytes()
        with patch('fruitfly_agent.run.configuration.profile.save_specification', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                save_harness_config(self.path, config)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(list((self.root / 'components').rglob('*.yaml')))

    def test_ordinary_save_rejects_concurrently_changed_component(self):
        from fruitfly_agent.run.configuration.profile import save_harness_config
        self.write()
        config = load_system_config(self.path)
        (self.root / 'reduction.yaml').write_text('user edited concurrently')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            save_harness_config(self.path, config)

    def test_newly_enabled_default_component_stays_a_default_reference(self):
        from fruitfly_agent.runtime_spec import HarnessConfig
        from fruitfly_agent.runtime_spec.selections import MechanismSelection
        from fruitfly_agent.run.configuration.profile import save_harness_config
        self.write()
        config = load_system_config(self.path)
        profile = config.select()
        profile = replace(profile, mechanisms=(*profile.mechanisms, MechanismSelection('subagent')))
        save_harness_config(self.path, HarnessConfig('baseline', {'baseline': profile}))
        raw = yaml.safe_load(self.path.read_text())['profiles']['baseline']
        self.assertEqual(raw['H']['subagent'], {'default': True})
        self.assertEqual(raw['models']['roles']['subagent'], {'inherit': 'executor'})

    def test_changed_file_component_keeps_its_location_and_repeated_saves_work(self):
        from fruitfly_agent.runtime_spec import HarnessConfig
        from fruitfly_agent.run.configuration.profile import save_harness_config
        self.write()
        profile = load_system_config(self.path).select()
        profile = replace(profile, mechanisms=tuple(replace(m, parameters={**m.parameters, 'tail_tokens': 768})
            if m.mechanism_id == 'layered-compaction' else m for m in profile.mechanisms))
        save_harness_config(self.path, HarnessConfig('baseline', {'baseline': profile}))
        reloaded = load_system_config(self.path)
        save_harness_config(self.path, reloaded)
        raw = yaml.safe_load(self.path.read_text())['profiles']['baseline']
        self.assertEqual(raw['H']['layered-compaction'], {'file': 'reduction.yaml'})
        self.assertEqual(yaml.safe_load((self.root / 'reduction.yaml').read_text())['parameters']['settings']['tail_tokens'], 768)
