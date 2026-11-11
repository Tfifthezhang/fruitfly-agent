"""Default intent, typed candidates and frozen H/S/I reach ordinary execution."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.session import Session
from fruitfly_agent.lab.catalog import (builtin_catalog, load_system_config, materialize_system,
    component_profile, configuration_inventory, PermissionPolicy)
from fruitfly_agent.runtime_spec import load_harness_config, HarnessConfig
from fruitfly_agent.runtime_spec import documents
from fruitfly_agent.run.configuration import save_harness_config
from tests.support.assembly import AssemblyWorkspace
from tests.support.faux_provider import FauxProvider


class ParameterDefaultTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.workspace = AssemblyWorkspace(self.root)
        self.path = self.root / 'config.yaml'
        self.raw = {'default_profile': 'test', 'profiles': {'test': {
            'models': {'catalog': 'models.yaml', 'roles': {'executor': 'offline'}},
            'H': {name: {'default': True} for name in
                  ('local-env', 'read-tool', 'base_prompt', 'layered-compaction')},
            'S': {}, 'I': {name: {'default': True} for name in
                           ('improvement-editor', 'improvement-evaluator')}}}}
        self.write()

    def write(self):
        self.path.write_text(yaml.safe_dump(self.raw, sort_keys=False))

    @contextmanager
    def changed_defaults(self):
        original = documents._package_bytes

        def read(package, resource):
            data = original(package, resource)
            if package == 'fruitfly_agent.lab.base_prompt' and resource == 'defaults.yaml':
                value = yaml.safe_load(data)
                value['parameters']['instructions']['system'] = 'Updated owner instructions.'
                return yaml.safe_dump(value).encode()
            if package.endswith('.layered_compaction') and resource == 'defaults.yaml':
                value = yaml.safe_load(data)
                value['parameters']['settings']['trigger_ratio'] = .8
                return yaml.safe_dump(value).encode()
            return data

        with patch.object(documents, '_package_bytes', side_effect=read):
            yield

    async def execute(self, profile, *, label):
        provider = FauxProvider()
        provider.respond_text('done')
        self.workspace.registry.create.side_effect = lambda *_: provider
        owned = []
        with Session(self.root / (label + '.jsonl')) as session:
            runtime = self.workspace.assemble(profile, session, catalog=builtin_catalog(),
                resource_sink=owned, permission_policy=PermissionPolicy.unrestricted(self.root))
            try:
                result = await run_agent_loop(runtime.config, [UserMessage('Inspect the supplied evidence.')],
                                              context_pipeline=runtime.context_pipeline)
                self.assertFalse(result.is_error)
                reducer = runtime.components['layered-compaction-state']
                base = provider.calls[0]['system_prompt'].rstrip()
                return base, reducer.config.trigger_ratio
            finally:
                for resource in reversed(owned):
                    closer = getattr(resource, 'aclose', None) or getattr(resource, 'close', None)
                    if closer:
                        result = closer()
                        if hasattr(result, '__await__'):
                            await result

    async def test_save_preserves_default_intent_and_text_and_number_updates_reach_execution(self):
        self.assertFalse(load_harness_config(self.path).select().configured)
        config = load_system_config(self.path)
        save_harness_config(self.path, config)
        saved = yaml.safe_load(self.path.read_text())['profiles']['test']
        for role, name in (('H', 'base_prompt'), ('H', 'layered-compaction'), ('I', 'improvement-editor')):
            self.assertEqual(saved[role][name], {'default': True})
        with self.changed_defaults():
            profile = load_system_config(self.path).select()
            prompt, ratio = await self.execute(profile, label='updated')
            self.assertIn('Updated owner instructions.', prompt)
            self.assertEqual(ratio, .8)
            rows = configuration_inventory(profile, builtin_catalog())
            row = next(row for row in rows if row['id'] == 'layered-compaction')
            self.assertEqual(row['source_kind'], 'default')
            self.assertFalse(row['fields']['parameters.settings.trigger_ratio']['configured'])

    async def test_frozen_bundle_preserves_full_typed_values_and_roles_after_defaults_change(self):
        baseline = load_system_config(self.path).select()
        original = await self.execute(baseline, label='reference')
        destination = self.root / 'frozen/config.yaml'
        materialize_system(baseline, destination, model_source=self.workspace.model_path)
        raw = yaml.safe_load(destination.read_text())['profiles']['test']
        for role in ('H', 'S', 'I'):
            for reference in raw[role].values():
                self.assertEqual(set(reference), {'inline'})
                self.assertEqual(reference['inline']['role'], role)
        with self.changed_defaults():
            frozen = load_system_config(destination).select()
            self.assertEqual(await self.execute(frozen, label='frozen'), original)

    async def test_explicit_value_equal_to_default_keeps_explicit_intent(self):
        baseline = load_system_config(self.path).select()
        base = next(d for d in baseline.component_documents if d.id == 'base_prompt')
        self.raw['profiles']['test']['H']['base_prompt'] = {'inline': base.to_dict()}
        self.write()
        config = load_system_config(self.path)
        original = await self.execute(config.select(), label='explicit')
        save_harness_config(self.path, config)
        saved = yaml.safe_load(self.path.read_text())['profiles']['test']['H']['base_prompt']
        self.assertEqual(set(saved), {'file'})
        self.assertNotIn('default', saved)
        with self.changed_defaults():
            prompt, _ = await self.execute(load_system_config(self.path).select(), label='still-explicit')
            self.assertEqual(prompt, original[0])

    def test_role_tampering_ambiguous_references_and_false_default_are_rejected(self):
        for reference in ({'default': False}, {'default': True, 'inline': {}}, {'default': 1}):
            with self.subTest(reference=reference):
                self.raw['profiles']['test']['H']['base_prompt'] = reference
                self.write()
                with self.assertRaises(ValueError):
                    load_system_config(self.path)
        self.raw['profiles']['test']['H'].pop('base_prompt')
        self.raw['profiles']['test']['S']['base_prompt'] = {'default': True}
        self.write()
        with self.assertRaisesRegex(ValueError, 'role'):
            load_system_config(self.path)

    def test_stale_default_receipts_reject_freezing_and_disabled_reference_stays_disabled(self):
        self.raw['profiles']['test']['H']['layered-compaction']['enabled'] = False
        self.write()
        baseline = load_system_config(self.path).select()
        self.assertFalse(next(s for s in baseline.mechanisms if s.mechanism_id == 'layered-compaction').enabled)
        saved = component_profile(baseline, builtin_catalog()).to_dict()
        self.assertEqual(saved['H']['layered-compaction'], {'default': True, 'enabled': False})
        with self.changed_defaults(), self.assertRaisesRegex(ValueError, 'source changed'):
            materialize_system(baseline, self.root / 'stale/config.yaml')

    def test_persisted_parameter_binding_keeps_runtime_identity_after_reload(self):
        from fruitfly_agent.run import DataArtifactStore
        store = DataArtifactStore(self.root / '.fruitfly/artifacts')
        profile = load_system_config(self.path).select()
        reference = store.put_text('A verified explicit procedure.')
        profile = replace(profile, prompt=reference.artifact_id)
        def digest(profile):
            with Session(self.root / 'same-session.jsonl') as session:
                runtime = self.workspace.assemble(profile, session, catalog=builtin_catalog(),
                    artifact_store=store, permission_policy=PermissionPolicy.unrestricted(self.root))
                try:
                    return runtime.manifest.digest
                finally:
                    runtime.config.readable_resources.close()
        original = digest(profile)
        save_harness_config(self.path, HarnessConfig('test', {'test': profile}), artifact_reader=store.read_text)
        self.assertEqual(digest(load_system_config(self.path).select()), original)

    def test_run_source_snapshot_loads_owner_parameters_without_checkout_fallback(self):
        import subprocess
        import sys
        from fruitfly_agent.run.storage.snapshots import capture_source_tree, SnapshotStore
        from fruitfly_agent.run import DataArtifactStore
        snapshot = capture_source_tree(Path(__file__).resolve().parents[2])
        paths = {entry.path for entry in snapshot.files}
        self.assertIn('fruitfly_agent/lab/base_prompt/defaults.yaml', paths)
        self.assertIn('fruitfly_agent/improvement/contracts/defaults.yaml', paths)
        self.assertIn('fruitfly_agent/lab/improvement/assessment/methods/model/defaults.yaml', paths)
        self.assertIn('fruitfly_agent/lab/improvement/editor/methods/workspace/defaults.yaml', paths)
        store = SnapshotStore(DataArtifactStore(self.root / 'source-artifacts'))
        frozen = store.materialize(store.put(snapshot), self.root / 'source')
        code = '''
from pathlib import Path
import sys
root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from fruitfly_agent.lab.catalog import builtin_catalog
from fruitfly_agent.lab.catalog.defaults import read_default
from fruitfly_agent.lab.context_manager.reduction.methods.working_memory import config
assert Path(config.__file__).is_relative_to(root)
assert config.WorkingMemoryConfig().maintenance_ratio == .5
from fruitfly_agent.improvement.contracts.plans import StageTimeouts
from fruitfly_agent.lab.improvement.editor import AgentEditor
from fruitfly_agent.lab.improvement.assessment import ModelEvaluator
assert StageTimeouts().editor_seconds == 1200
for cls in (AgentEditor, ModelEvaluator):
    module = sys.modules[cls.__module__]
    assert Path(module.__file__).is_relative_to(root)
catalog = builtin_catalog()
for name, role in [('base_prompt','H'), ('skill-library','S'), ('improvement-editor','I'), ('improvement-organizer','I')]:
    assert read_default(catalog, name)[0].role == role
from fruitfly_eval.improvement import materials
from fruitfly_agent.interactive.terminal.features import composer
from fruitfly_agent.run.runtime import clipboard
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_eval.improvement.evidence import answer_evidence
for module in (materials, composer, clipboard):
    assert Path(module.__file__).is_relative_to(root)
archive = root / 'fixture-archive'
agent = archive / 'artifacts/harbor/job/trial/agent'
agent.mkdir(parents=True, exist_ok=True)
(agent / 'session.jsonl').write_text('{"message":{"role":"assistant","content":"done","stopReason":"stop"}}')
artifacts = MemoryArtifacts()
resources, _ = materials.collect_materials(archive, artifacts)
assert answer_evidence(resources, artifacts)['text'] == 'done'
assert composer.Composer(None).prepare('text') == 'text'
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(frozen)],
                                cwd=self.root, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        (frozen / 'fruitfly_agent/lab/base_prompt/defaults.yaml').unlink()
        missing = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(frozen)],
                                 cwd=self.root, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn('defaults.yaml', missing.stderr)

    def test_role_settings_roundtrip_and_frozen_defaults_preserve_authored_configuration(self):
        for role_id, values in (('improvement-editor', {'target_page_entries': 3}),
                                ('improvement-evaluator', {'output_preview_characters': 5})):
            self.raw['profiles']['test']['I'][role_id] = {'inline': {
                'id': role_id, 'role': 'I', 'implementation': role_id,
                'parameters': {'settings': values}}}
        self.write()
        config = load_system_config(self.path)
        save_harness_config(self.path, config)
        original = self.path.read_bytes()
        selected = load_system_config(self.path).select()
        self.assertEqual(3, selected.component_settings['editor']['settings']['target_page_entries'])
        self.assertEqual(5, selected.component_settings['evaluator']['settings']['output_preview_characters'])
        destination = self.root / 'role-frozen/config.yaml'
        materialize_system(selected, destination, model_source=self.workspace.model_path)
        restored = load_system_config(destination).select()
        self.assertEqual(selected.component_settings, restored.component_settings)
        self.assertEqual(original, self.path.read_bytes())
