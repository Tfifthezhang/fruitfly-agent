"""Per-job method selection uses normal previews, execution and adoption."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.algorithms import AlgorithmSpec
from fruitfly_agent.lab.improvement.methods import MethodDefinition
from fruitfly_agent.lab.improvement.methods.opro import definition as opro_definition
from fruitfly_agent.lab.improvement.contracts.search import SearchCandidate, SearchResult
from tests.support.improvers import offline_factory


class Probe:
    spec = AlgorithmSpec('probe-search', 'probe-v1', 'session')
    supported_roles = frozenset({'H'})
    supported_schemas = frozenset({'text-v1'})
    required_capabilities = frozenset({'evaluate', 'history'})

    async def search(self, problem, services):
        baseline = await services.evaluate(problem.baseline.text, 'validation')
        result = await services.evaluate('Candidate instructions', 'validation')
        return SearchResult((SearchCandidate('Candidate instructions', result.score),), baseline.score)


def probe_definition():
    original = opro_definition()
    return replace(original,
        descriptor=replace(original.descriptor, mechanism_id='probe-search', label='Probe'),
        implementation_id='probe-v1',
        improvement=MethodDefinition(Probe.supported_roles, Probe.supported_schemas,
            Probe.required_capabilities, lambda binding: binding.text_host(Probe(), label='Probe')))


class ImprovementMethodTests(unittest.IsolatedAsyncioTestCase):
    async def test_temporary_method_and_target_reach_review_activation_and_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            factory = offline_factory(root, 'opro', definition=probe_definition())
            app = AgentApplication(factory)
            await app.start()
            try:
                configured = factory._current_improver
                original_manifest = app.runtime_manifest
                original_config = factory.selection.config_path.read_bytes()
                options = app.improvement_methods('H', 'skill-catalog.guidance')
                self.assertEqual({m.method_id for m in options if m.available}, {'opro', 'probe-search', 'tree-search'})
                self.assertFalse(app.improvement_methods('S', 'skill-catalog.guidance')[0].available)
                preview = app.improvement_preview(direction='Improve', method_id='probe-search',
                    target_id='skill-catalog.guidance', parameters={'rounds': 1})
                self.assertEqual((preview.algorithm, preview.target), ('probe-search', 'skill-catalog.guidance'))
                self.assertEqual(configured.config.provider.calls, [])
                configured.config.provider.respond_text('wrong')
                configured.config.provider.respond_text('B')
                records = await app.start_improvement('Improve', preview_token=preview.preview_token)
                self.assertEqual(records[0].algorithm, 'probe-search')
                self.assertEqual(records[0].target, 'skill-catalog.guidance')
                self.assertIs(factory._current_improver, configured)
                self.assertEqual(app.runtime_manifest, original_manifest)
                self.assertEqual(factory.selection.config_path.read_bytes(), original_config)
                with self.assertRaisesRegex(ValueError, 'consumed'):
                    await app.improve('Improve', preview_token=preview.preview_token)
                await app.adopt_candidate(records[0].candidate_id)
                self.assertEqual(factory._current_targets['skill-catalog.guidance'].snapshot().text,
                                 'Candidate instructions')
                factory._current_improver.config.provider.respond_text('done')
                await app.submit('Continue with the selected candidate')
                path = Path(app.status.session_path)
            finally:
                await app.close()
            restored = AgentApplication(factory)
            await restored.start(resume=True, session_path=path)
            try:
                self.assertEqual(factory._current_targets['skill-catalog.guidance'].snapshot().text,
                                 'Candidate instructions')
                self.assertEqual(factory._current_improver.spec.algorithm_id, 'opro')
            finally:
                await restored.close()

    async def test_unknown_method_invalid_parameters_and_changed_binding_make_no_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = offline_factory(Path(tmp), 'opro', definition=probe_definition())
            app = AgentApplication(factory)
            await app.start()
            try:
                for selection in ({'method_id': 'not-installed'}, {'parameters': {'unknown': True}},
                                  {'target_id': 'missing'}):
                    with self.assertRaises(ValueError):
                        app.improvement_preview(direction='Improve', **selection)
                preview = app.improvement_preview(direction='Improve')
                factory._current_improver.parameters['rounds'] += 1
                with self.assertRaisesRegex(ValueError, 'method changed'):
                    await app.improve('Improve', preview_token=preview.preview_token)
                self.assertEqual(factory._current_improver.config.provider.calls, [])
                self.assertEqual(app.candidates(), ())
            finally:
                await app.close()

    async def test_unconfigured_method_runs_remembers_parameters_and_activates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            factory = offline_factory(root, 'opro', definition=probe_definition())
            factory.configuration.set_mechanism('opro', enabled=False)
            factory.configuration.save()
            factory.reload_configuration()
            original_config = factory.selection.config_path.read_bytes()
            app = AgentApplication(factory)
            await app.start()
            try:
                self.assertIsNone(factory._current_improver.host)
                before = factory.system_version()
                preview = app.improvement_preview(direction='Improve', method_id='probe-search',
                    target_id='base_prompt', parameters={'rounds': 1})
                provider = factory._current_runtime_config.provider
                self.assertEqual(provider.calls, [])
                provider.respond_text('wrong')
                provider.respond_text('B')
                records = await app.improve('Improve', preview_token=preview.preview_token)
                self.assertEqual(len(records), 1)
                self.assertEqual(factory.system_version(), before)
                self.assertIsNone(factory._current_improver.host)
                self.assertEqual(factory.selection.config_path.read_bytes(), original_config)
                self.assertEqual(factory._current_components['improvement-methods'].bound, [])
            finally:
                await app.close()
            app = AgentApplication(factory)
            await app.start()
            try:
                option = app.improvement_methods('H', 'base_prompt')[0]
                self.assertEqual(option.method_id, 'probe-search')
                self.assertTrue(option.default)
                selected = factory.select_improvement_method(method_id='probe-search', target_id='base_prompt')
                self.assertEqual(selected.parameters['rounds'], 1)
                await app.adopt_candidate(records[0].candidate_id)
                self.assertEqual(factory._current_targets['base_prompt'].snapshot().text, 'Candidate instructions')
            finally:
                await app.close()

    async def test_evicted_previews_release_their_temporary_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = offline_factory(Path(tmp), 'opro', definition=probe_definition())
            app = AgentApplication(factory)
            await app.start()
            try:
                for _ in range(17):
                    app.improvement_preview(direction='Improve', method_id='probe-search', target_id='base_prompt')
                methods = factory._current_components['improvement-methods']
                self.assertEqual(len(methods.bound), 16)
                self.assertEqual(factory._current_runtime_config.provider.calls, [])
                with self.assertRaises(ValueError):
                    app.improvement_preview(direction='Improve', method_id='probe-search', pack_id='missing')
                self.assertEqual(len(methods.bound), 16)
            finally:
                await app.close()
