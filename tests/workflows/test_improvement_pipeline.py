"""Normal Application and menu consume the same replaceable component workflow."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest
from fruitfly_agent.lab.improvement.api import (WorkflowBindings, GeneratorRegistry,
    CandidateBundle, HarnessSnapshot, ComponentFile, EditReason, ProposalResult)
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.faux_provider import FauxProvider
from tests.support.materials import _write_models
from tests.support.task_packs import install


class LocalRule:
    generator_id = 'local-rule'
    required_capabilities = frozenset()
    label = 'Local rule editor'

    async def propose(self, request, services):
        documents = tuple(replace(c, files=(ComponentFile('instructions.txt', 'Read the input before completing the task.'),))
            if c.component_id in request.plan.component_ids else c for c in request.baseline.components)
        return ProposalResult((CandidateBundle(request.plan.parent, request.baseline,
            HarnessSnapshot(documents), self.generator_id,
            tuple(EditReason(name, 'Reference skipped a source', (request.records[0].run_id,))
                  for name in request.plan.component_ids)),))


class ComposeFirst:
    async def compose(self, request, services):
        return request.candidates[0]


class NoEntry:
    async def reflect(self, outcome):
        return ()


class ApplicationPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_persistent_candidate_verifies_adopts_and_recovers_exact_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_models(root)
            install(root)
            provider = FauxProvider()
            for output in ('wrong', 'A', 'A', 'A', 'wrong', 'A', 'wrong', 'B', 'wrong', 'SECRET_ANSWER'):
                provider.respond_text(output)
            providers = Mock()
            providers.create.return_value = provider
            generators = GeneratorRegistry()
            generators.register('local-rule', LocalRule)
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=providers,
                improvement_bindings=WorkflowBindings(generators=generators,
                    composer=lambda plan, services: ComposeFirst(), reflector=lambda plan, services: NoEntry()))
            factory.configuration.save()
            factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            try:
                parent = factory.system_version()
                request = WorkflowRequest(component_ids=('base_prompt',), generator_id='local-rule',
                    task_pack_id='project', scope='persistent')
                preview = app.workflow_preview(request)
                records = await app.improve('', preview_token=preview.preview_token)
                self.assertEqual(len(records), 1)
                self.assertEqual(factory.system_version(), parent)
                declared = factory._versions.versions.read_candidate(dict(records[0].evidence)['Version candidate'])
                self.assertEqual((declared.version.improver, declared.version.state), (parent.improver, parent.state))
                await app.adopt_candidate(records[0].candidate_id)
                self.assertEqual(factory.system_version(), declared.version)
                self.assertEqual(factory._current_runtime_config.system_prompt, 'Read the input before completing the task.')
                provider.respond_text('done')
                await app.submit('Continue with the adopted component')
                session = Path(app.status.session_path)
            finally:
                await app.close()
            await app.start(resume=True, session_path=session)
            try:
                self.assertEqual(factory.system_version(), declared.version)
            finally:
                await app.close()

    async def test_current_task_file_execution_history_and_unchanged_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_models(root)
            (root / 'input.txt').write_text('Original task source')
            provider = FauxProvider()
            for text in ('reference output', 'candidate output', 'candidate output', 'composed output'):
                provider.respond_tool_call('read', {'path': 'input.txt'})
                provider.respond_text(text)
            providers = Mock()
            providers.create.return_value = provider
            generators = GeneratorRegistry()
            generators.register('local-rule', LocalRule)
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=providers,
                improvement_bindings=WorkflowBindings(generators=generators,
                    composer=lambda plan, services: ComposeFirst(), reflector=lambda plan, services: NoEntry()))
            factory.configuration.save()
            factory.reload_configuration()
            original = factory.selection.config_path.read_bytes()
            app = AgentApplication(factory)
            await app.start()
            try:
                parent = factory.system_version()
                options = app.workflow_configuration()
                self.assertEqual([g.choice_id for g in options.generators], ['local-rule'])
                self.assertFalse(next(c for c in options.components if c.component_id == 'tool-guidance.bash').available)
                request = WorkflowRequest('Read input.txt and complete the task.', ('input.txt',), ('base_prompt',),
                                          generator_id='local-rule')
                preview = app.workflow_preview(request)
                self.assertEqual(provider.calls, [])
                self.assertEqual(await app.improve('', preview_token=preview.preview_token), ())
                self.assertEqual(factory._component_jobs.outcome.selected.output.strip(), 'composed output')
                self.assertEqual(factory.system_version(), parent)
                self.assertEqual(factory.selection.config_path.read_bytes(), original)
                self.assertEqual((root / 'input.txt').read_text(), 'Original task source')
                result = app.improvement_history()[0]
                self.assertIn('composed output', next(s.text for s in result.sections if s.title == 'Task output'))
                self.assertEqual(len(provider.calls), 8)
                for call in provider.calls[1::2]:
                    self.assertIn('Original task source', repr(call['messages']))
                with self.assertRaisesRegex(ValueError, 'unknown|consumed'):
                    await app.improve('', preview_token=preview.preview_token)
            finally:
                await app.close()

    async def test_changed_plan_and_unavailable_verification_fail_before_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_models(root)
            provider = FauxProvider()
            providers = Mock()
            providers.create.return_value = provider
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=providers)
            app = AgentApplication(factory)
            await app.start()
            try:
                request = WorkflowRequest('Do work', component_ids=('base_prompt',), scope='persistent')
                with self.assertRaisesRegex(ValueError, 'independent verification'):
                    app.workflow_preview(request)
                request = replace(request, scope='task')
                preview = app.workflow_preview(request)
                with self.assertRaisesRegex(ValueError, 'conditions changed'):
                    await app.improve('changed guidance', preview_token=preview.preview_token)
                self.assertEqual(provider.calls, [])
            finally:
                await app.close()

    async def test_experience_commits_at_task_boundary_and_next_task_gets_common_baseline(self):
        from fruitfly_agent.lab.improvement.api import ExperienceEntry, experience_id
        class Remember:
            async def reflect(self, outcome):
                return (ExperienceEntry('lesson-' + outcome.plan.job_id, outcome.task.task_id,
                    'Input inspection', 'Read the source before delivery',
                    (outcome.records[0].run_id, outcome.selected.run_id), outcome.harness),)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_models(root)
            provider = FauxProvider()
            providers = Mock()
            providers.create.return_value = provider
            generators = GeneratorRegistry()
            requests = []
            class RecordRule(LocalRule):
                async def propose(self, request, services):
                    requests.append(request)
                    return await super().propose(request, services)
            generators.register('local-rule', RecordRule)
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=providers,
                improvement_bindings=WorkflowBindings(generators=generators,
                    composer=lambda *args: ComposeFirst(), reflector=lambda *args: Remember()))
            app = AgentApplication(factory)
            await app.start()
            try:
                initial = factory.system_version()
                original = factory._current_runtime_config.system_prompt
                for _ in range(2):
                    for text in ('reference', 'probe', 'probe', 'final'):
                        provider.respond_text(text)
                    preview = app.workflow_preview(WorkflowRequest('Complete a file task.',
                        component_ids=('base_prompt',), generator_id='local-rule'))
                    await app.improve('', preview_token=preview.preview_token)
                current = factory.system_version()
                self.assertEqual((initial.harness, initial.improver), (current.harness, current.improver))
                self.assertNotEqual(initial.state, current.state)
                self.assertEqual(len(factory._experience_store.snapshot()), 2)
                self.assertEqual(len(requests[0].experience), 0)
                self.assertEqual(len(requests[2].experience), 1)
                self.assertEqual(requests[2].baseline.component('base_prompt').files[0].text, original)
                self.assertEqual(factory._current_runtime_config.system_prompt, original)
            finally:
                await app.close()

    async def test_factory_resources_close_when_a_later_stage_construction_fails(self):
        from tests.support.improvers import offline_factory, OfflineRunner
        closed = []
        class ResourceRunner(OfflineRunner):
            async def aclose(self):
                closed.append('runner')
        def fail(*args):
            raise RuntimeError('Composer construction failed')
        with tempfile.TemporaryDirectory() as directory:
            factory = offline_factory(Path(directory))
            factory._component_jobs.runner_factory = lambda *args: ResourceRunner()
            factory._component_jobs.composer_factory = fail
            app = AgentApplication(factory)
            await app.start()
            try:
                preview = app.workflow_preview(factory.test_request)
                with self.assertRaisesRegex(RuntimeError, 'Composer construction failed'):
                    await app.improve('', preview_token=preview.preview_token)
                self.assertEqual(closed, ['runner'])
                self.assertIn('Composer construction failed', '\n'.join(s.text for s in app.improvement_history()[0].sections))
                self.assertIsNone(factory._component_jobs.services)
            finally:
                await app.close()
