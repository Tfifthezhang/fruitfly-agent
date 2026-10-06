"""Capability substitution, construction failure ownership and owner-loop model I/O."""
import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fruitfly_agent.lab.catalog import builtin_catalog, MechanismDefinition, MechanismDescriptor, MechanismContribution, MechanismSelection
from fruitfly_agent.lab.environment import LocalEnv
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.materials import _write_models
from tests.support.faux_provider import FauxProvider


class ContractBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_alternative_environment_reuses_tools_and_ui_dependency_controls(self):
        definition = MechanismDefinition(
            MechanismDescriptor('other-env', 'Other env', 'Alternative execution environment',
                contributions=(MechanismContribution('capability', 'environment'),), exclusive_group='environment', install_order=999),
            lambda state, context, params: replace(state, config=replace(state.config, env=LocalEnv(str(context.workspace)))),
            provides=frozenset({'execution-env'}),
        )
        catalog = builtin_catalog().extended((definition,))
        resolved = catalog.resolve((MechanismSelection('other-env'), MechanismSelection('read-tool')))
        self.assertEqual([i.definition.descriptor.mechanism_id for i in resolved], ['other-env', 'read-tool'])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_models(root)
            factory = RunApplicationFactory(cwd=root, environment={}, catalog=catalog)
            factory.configuration.set_mechanism('other-env', enabled=True)
            factory.configuration.set_mechanism('read-tool', enabled=True)
            items = {i.mechanism_id: i for i in factory.configuration.snapshot().mechanisms}
            self.assertTrue(items['other-env'].enabled)
            self.assertFalse(items['local-env'].enabled)
            factory.configuration.set_mechanism('other-env', enabled=False)
            items = {i.mechanism_id: i for i in factory.configuration.snapshot().mechanisms}
            self.assertFalse(items['read-tool'].enabled)

    async def test_installer_constructor_resource_is_cleaned_before_return(self):
        closed = []
        class Resource:
            def close(self):
                closed.append('resource')
        def fail(state, context, params):
            context.own(Resource())
            raise RuntimeError('failed after allocation')
        definition = MechanismDefinition(
            MechanismDescriptor('broken', 'Broken', 'Constructs then fails',
                contributions=(MechanismContribution('online', 'workflow'),), default_enabled=True), fail,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_models(root)
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()
            factory = RunApplicationFactory(cwd=root, environment={}, catalog=builtin_catalog().extended((definition,)), provider_registry=registry)
            with self.assertRaisesRegex(RuntimeError, 'failed after allocation'):
                await factory.open(resume=False, session_path=None)
        self.assertEqual(closed, ['resource'])


    async def test_returned_resources_close_when_later_contract_validation_fails(self):
        from fruitfly_agent.core.context import ContextStage
        from fruitfly_agent.lab.catalog import LabCatalog

        for source in ('installer', 'bootstrap', 'bootstrap-invalid'):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as tmp:
                closed = []
                class Resource:
                    def close(self):
                        closed.append(source)
                    async def transform(self, frame):
                        return frame
                resource = Resource()
                def invalid(state, context, params):
                    # This mechanism declared no context stage.
                    return state.with_component('resource', resource).with_context_stage(
                        ContextStage('broken', 'augmentation', resource))
                def fail(state, context, params):
                    raise RuntimeError('later installation failed')
                definition = MechanismDefinition(
                    MechanismDescriptor('broken', 'Broken', 'Reject assembled state',
                        contributions=(MechanismContribution('online', 'workflow'),), default_enabled=True),
                    invalid if source == 'installer' else fail,
                )
                base = builtin_catalog()
                bootstrap = base.bootstrap
                if source == 'bootstrap':
                    bootstrap = lambda state, context: base.bootstrap(state, context).with_component('resource', resource)
                elif source == 'bootstrap-invalid':
                    def bootstrap(state, context):
                        context.own(resource)
                        return None
                catalog = LabCatalog((*base.definitions(), definition), bootstrap=bootstrap)
                root = Path(tmp)
                _write_models(root)
                registry = Mock()
                registry.create.side_effect = lambda *_: FauxProvider()
                factory = RunApplicationFactory(cwd=root, environment={}, catalog=catalog, provider_registry=registry)
                with self.assertRaisesRegex((ValueError, RuntimeError, TypeError), 'undeclared context stages|later installation failed|bootstrap must return AssemblyState'):
                    await factory.open(resume=False, session_path=None)
                self.assertEqual(closed, [source])


    def test_capability_missing_ambiguous_and_cycle_rejected(self):
        catalog = builtin_catalog()
        with self.assertRaisesRegex(ValueError, 'exactly one provider'):
            catalog.resolve((MechanismSelection('read-tool'),))
        def definition(name, dependency):
            return MechanismDefinition(MechanismDescriptor(name, name, name,
                contributions=(MechanismContribution('online', 'workflow'),), requires=frozenset({dependency})), lambda s,c,p: s)
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            catalog.extended((definition('a', 'b'), definition('b', 'a'))).resolve((MechanismSelection('a'), MechanismSelection('b')))

    async def test_new_declared_artifact_slot_is_consumed_without_host_whitelist(self):
        from fruitfly_agent.run.artifacts import DataArtifactStore
        def install(state, context, params):
            artifact_id = context.artifact_bindings['extra.guidance']
            text = context.artifact_reader(artifact_id)
            return state.with_data_artifact({'key': 'extra.guidance', 'id': artifact_id,
                'media_type': 'text/plain; charset=utf-8', 'size_bytes': len(text.encode('utf-8'))})
        definition = MechanismDefinition(
            MechanismDescriptor('extra-source', 'Extra source', 'Declared text slot',
                contributions=(MechanismContribution('capability', 'context'),), default_enabled=True), install,
            artifact_slots=frozenset({'extra.guidance'}),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_models(root)
            store = DataArtifactStore(root / '.fruitfly' / 'artifacts')
            reference = store.put_text('frozen extra guidance').artifact_id
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()
            factory = RunApplicationFactory(cwd=root, environment={}, catalog=builtin_catalog().extended((definition,)), provider_registry=registry, data_artifact_bindings={'extra.guidance': reference})
            handle = await factory.open(resume=False, session_path=None)
            await handle.start()
            self.assertEqual(handle.manifest['data_artifacts'][0]['id'], reference)
            await handle.close()


    def test_public_identity_and_definition_metadata_reject_invalid_values(self):
        from fruitfly_agent.lab.algorithms import AlgorithmSpec
        from fruitfly_agent.lab.catalog import LabCatalog
        with self.assertRaisesRegex(TypeError, 'bootstrap must be callable'):
            LabCatalog((), bootstrap=1)
        with self.assertRaises(ValueError):
            AlgorithmSpec(' ', 'v1')
        definition = builtin_catalog().get('read-tool')
        with self.assertRaises(TypeError):
            replace(definition, visible='hidden')
        with self.assertRaises(ValueError):
            replace(definition, artifact_slots='one.slot')
        with self.assertRaises(ValueError):
            replace(definition, requires_capabilities=['invalid capability'])
        self.assertEqual(replace(definition, artifact_slots=['one.slot']).artifact_slots, frozenset({'one.slot'}))
        self.assertEqual(replace(definition, provides=iter(['extra-capability'])).provides, frozenset({'extra-capability'}))
