"""I experiments use actual editor bindings, private trials and real activation."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
import asyncio
from unittest.mock import patch

from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.rsi import EvolutionEngine
from fruitfly_agent.run.evolution import RunEvolutionHost
from tests.support.self_improver import experiment_factory
from tests.support.self_improver import ProceduralProvider
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
from fruitfly_agent.core.model_stream import AssistantMessageEventStream


class EditorEvolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_configured_i_candidate_activates_and_reloads_with_matching_identity(self):
        import yaml
        from fruitfly_agent.run.application import RunApplicationFactory
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            factory, provider, request = experiment_factory(root)
            path = root / '.fruitfly/config.yaml'
            document = yaml.safe_load(path.read_text())
            profile = document['profiles'][document['default_profile']]
            profile['I']['improvement-editor'] = {'inline': {
                'id': 'improvement-editor', 'role': 'I', 'implementation': 'improvement-editor', 'parameters': {}}}
            path.write_text(yaml.safe_dump(document))
            factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            try:
                candidate = (await app.improve('', preview_token=app.workflow_preview(request).preview_token))[0]
                await app.adopt_candidate(candidate.candidate_id)
                self.assertEqual(factory.candidate_store.read(candidate.candidate_id).status, 'adopted')
            finally:
                await app.close()
            fresh = RunApplicationFactory(cwd=root, environment={}, provider_registry=factory.provider_registry,
                improvement_bindings=factory.improvement_bindings)
            restored = AgentApplication(fresh)
            await restored.start()
            try:
                self.assertEqual(fresh._current_components['component-improvement-editor-instructions'].invariant.count('STEP'), 1)
            finally:
                await restored.close()

    async def test_file_runner_override_does_not_change_editor_execution_capabilities(self):
        from fruitfly_agent.lab.improvement.execution.file_runner import FileTaskRunner
        class FileOverride:
            capabilities = FileTaskRunner.capabilities
            def __call__(self, *args):
                raise AssertionError('discovery must not construct a runner')
        with tempfile.TemporaryDirectory() as directory:
            factory, provider, request = experiment_factory(Path(directory))
            factory._component_jobs.runner_factory = FileOverride()
            app = AgentApplication(factory)
            await app.start()
            self.addAsyncCleanup(app.close)
            options = app.workflow_configuration()
            editor = next(v for v in options.executions if v.execution_id == 'improver-comparison')
            self.assertEqual(editor.component_ids, ('improvement-editor',))
            self.assertTrue(app.workflow_preview(request).preview_token)
            self.assertEqual(provider.calls, [])

    async def test_material_order_preserves_use_limit_and_invalid_manifests_make_no_requests(self):
        from fruitfly_agent.lab.improvement.improver.materials import freeze
        from tests.support.task_packs import install, package
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            factory, provider, request = experiment_factory(root, uses=1)
            app = AgentApplication(factory)
            await app.start()
            self.addAsyncCleanup(app.close)
            extra = package()
            extra.update(id='extra', name='Extra independent episode', compatible_targets=['base_prompt'])
            for partition in ('train', 'validation', 'holdout'):
                extra[partition] = [dict(id=partition + '-1', input='extra ' + partition, expected='A')]
            install(root, extra)
            path = root / '.fruitfly/improvement/experiments/editor/experiment.json'
            manifest = json.loads(path.read_text())
            manifest['verification'].append('extra')
            path.write_text(json.dumps(manifest))
            context = factory._component_jobs.context()
            original = freeze(context, 'editor', 'base_prompt')
            factory._component_jobs.verification_uses.claim(original.verification_key, 1)
            manifest['verification'].reverse()
            path.write_text(json.dumps(manifest, indent=2))
            reordered = freeze(context, 'editor', 'base_prompt')
            self.assertNotEqual(original.source_id, reordered.source_id)
            self.assertEqual(original.verification_key, reordered.verification_key)
            with self.assertRaisesRegex(ValueError, 'use limit'):
                app.workflow_preview(request)
            extra['train'][0]['input'] = 'development training level1'
            install(root, extra)
            with self.assertRaisesRegex(ValueError, 'overlap'):
                freeze(context, 'editor', 'base_prompt')
            path.write_text(json.dumps(manifest).replace('{', '{"id":"duplicate",', 1))
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                freeze(context, 'editor', 'base_prompt')
            self.assertEqual(provider.calls, [])

    async def test_saved_default_reconciles_exact_editor_bytes_after_fresh_start(self):
        from fruitfly_agent.run.application import RunApplicationFactory
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            factory, provider, request = experiment_factory(root)
            app = AgentApplication(factory)
            await app.start()
            try:
                preview = app.workflow_preview(request)
                candidate = (await app.improve('', preview_token=preview.preview_token))[0]
                app.candidate_action(candidate.candidate_id, 'adopt')
            finally:
                await app.close()
            restored_factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=factory.provider_registry,
                improvement_bindings=factory.improvement_bindings)
            restored = AgentApplication(restored_factory)
            await restored.start()
            try:
                self.assertEqual(restored_factory.candidate_store.read(candidate.candidate_id).status, 'adopted')
                self.assertEqual(restored_factory._current_components['component-improvement-editor-instructions'].invariant.count('STEP'), 1)
            finally:
                await restored.close()

    async def test_failed_independent_comparison_cannot_publish_or_reuse_suite(self):
        original = ProceduralProvider.reply
        def fail_private(provider, ctx, *, signal=None):
            if 'list_files' not in {t.name for t in ctx.tools} and 'independent' in repr(ctx.messages):
                return AssistantMessageEventStream(provider._message_stream(
                    AssistantMessage(content=[TextBlock(text='wrong')], stop_reason='stop')))
            return original(provider, ctx, signal=signal)
        with tempfile.TemporaryDirectory() as directory:
            factory, provider, request = experiment_factory(Path(directory), uses=1)
            app = AgentApplication(factory)
            await app.start()
            self.addAsyncCleanup(app.close)
            parent = factory.system_version()
            with patch.object(ProceduralProvider, 'reply', fail_private):
                preview = app.workflow_preview(request)
                self.assertEqual(await app.improve('', preview_token=preview.preview_token), ())
            self.assertEqual(factory._component_jobs.outcome.stop_reason, 'verification_failed')
            self.assertIsNone(factory._component_jobs.outcome.decision)
            self.assertEqual(factory.system_version(), parent)
            self.assertEqual(app.candidates(), ())
            calls = len(provider.calls)
            with self.assertRaisesRegex(ValueError, 'use limit'):
                app.workflow_preview(request)
            self.assertEqual(len(provider.calls), calls)

    async def test_cancellation_closes_inner_episode_without_production_changes(self):
        from fruitfly_agent.lab.improvement.execution import builtin_executions, ExecutionRegistry
        entered, closed = asyncio.Event(), asyncio.Event()
        class HangingEpisode:
            def __init__(self, *args):
                pass
            async def run(self, request, *, budget, signal):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    closed.set()
        with tempfile.TemporaryDirectory() as directory:
            factory, provider, request = experiment_factory(Path(directory))
            definitions = builtin_executions().definitions()
            original = definitions[1]
            def build(context, prepared):
                ports = original.build(context, prepared)
                ports.runner.episode_factory = HangingEpisode
                return ports
            factory._component_jobs.executions = ExecutionRegistry((definitions[0], replace(original, build=build)))
            app = AgentApplication(factory)
            await app.start()
            self.addAsyncCleanup(app.close)
            before = factory.system_version()
            preview = app.workflow_preview(request)
            job = app.start_improvement('', preview_token=preview.preview_token)
            await entered.wait()
            app.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await job
            self.assertTrue(closed.is_set())
            self.assertEqual(factory.system_version(), before)
            self.assertEqual(provider.calls, [])
            self.assertEqual(app.pending_experience(), ())

    async def test_reusable_proof_rejects_changed_material_and_wrong_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            factory, provider, request = experiment_factory(root)
            app = AgentApplication(factory)
            await app.start()
            self.addAsyncCleanup(app.close)
            preview = app.workflow_preview(request)
            view = (await app.improve('', preview_token=preview.preview_token))[0]
            record = factory.candidate_store.read(view.candidate_id)
            count = len(provider.calls)
            self.assertTrue(factory.verified_candidate(record, 'improver-paired-v1').passed)
            with self.assertRaisesRegex(ValueError, 'policy'):
                factory.verified_candidate(record, 'wrong-policy')
            path = root / '.fruitfly/improvement/task-packs/independent/holdout.json'
            path.write_text(path.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'material changed'):
                factory.verified_candidate(record, 'improver-paired-v1')
            self.assertEqual(len(provider.calls), count)

    async def test_rsi_reuses_completed_proof_and_advances_only_after_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            factory, provider, request = experiment_factory(Path(directory))
            app = AgentApplication(factory)
            await app.start()
            self.addAsyncCleanup(app.close)
            host = RunEvolutionHost(app, factory, policy_id='improver-paired-v1', request=request)
            result = await EvolutionEngine().evolve(host, job_id='editors', policy_id='improver-paired-v1',
                direction='Improve editing procedures', max_steps=2)
            self.assertEqual((result.phase, result.steps), ('complete', 2))
            self.assertEqual(factory._current_components['component-improvement-editor-instructions'].invariant.count('STEP'), 2)
            counts = [json.loads(p.read_text())['uses'] for p in (Path(directory) / '.fruitfly/improvement').glob('verification-uses.json')]
            self.assertEqual(list(counts[0].values()), [2])
            calls = len(provider.calls)
            resumed = await EvolutionEngine().evolve(host, job_id='editors', policy_id='improver-paired-v1',
                direction='Improve editing procedures', max_steps=2)
            self.assertEqual(resumed, result)
            self.assertEqual(len(provider.calls), calls)

    async def test_two_generations_load_editor_and_keep_inner_artifacts_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            factory, provider, request = experiment_factory(root)
            app = AgentApplication(factory)
            await app.start()
            self.addAsyncCleanup(app.close)
            initial = factory.system_version()
            original_prompt = factory._current_runtime_config.system_prompt
            for generation in (1, 2):
                before = factory.system_version()
                calls = len(provider.calls)
                preview = app.workflow_preview(request)
                self.assertEqual(len(provider.calls), calls)
                records = await app.improve('', preview_token=preview.preview_token)
                outcome = factory._component_jobs.outcome
                self.assertEqual(outcome.decision.assurance, 'verified')
                self.assertEqual(len(records), 1)
                self.assertEqual(factory.system_version(), before)
                self.assertEqual(app.pending_experience(), ())
                self.assertEqual(factory._experience_store.snapshot(), ())
                self.assertEqual(factory._component_jobs.completion().report.model_calls, len(provider.calls) - calls)
                self.assertLessEqual(factory._component_jobs.completion().report.trial_calls, request.max_executions)
                job = root / '.fruitfly/improvement/jobs' / outcome.plan.job_id
                self.assertEqual(json.loads((job / 'plan.json').read_text())['schema_version'], 2)
                self.assertIn('independent-verification', (job / 'events.jsonl').read_text())
                # The development record exposes only measured reports, not private instructions.
                for record in outcome.records:
                    for resource in record.artifacts:
                        self.assertNotIn('independent training', factory.artifact_store.read_text(resource.artifact_id))
                await app.adopt_candidate(records[0].candidate_id)
                current = factory.system_version()
                self.assertEqual((current.harness, current.state), (initial.harness, initial.state))
                self.assertNotEqual(current.improver, before.improver)
                instructions = factory._current_components['component-improvement-editor-instructions']
                self.assertEqual(instructions.invariant.count('STEP'), generation)
                self.assertEqual(factory._current_runtime_config.system_prompt, original_prompt)
            self.assertEqual(len(app.improvement_history()), 2)

    async def test_invalid_scope_material_changes_and_insufficient_budget_make_no_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            factory, provider, request = experiment_factory(Path(directory))
            app = AgentApplication(factory)
            await app.start()
            self.addAsyncCleanup(app.close)
            for invalid in (replace(request, verification='behavior'), replace(request, max_model_calls=1),
                            replace(request, component_ids=('base_prompt', 'improvement-editor')),
                            replace(request, execution_parameters=(('inner_components', 'improvement-editor'),))):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    app.workflow_preview(invalid)
            preview = app.workflow_preview(request)
            path = Path(directory) / '.fruitfly/improvement/task-packs/independent/holdout.json'
            value = json.loads(path.read_text())
            value['holdout'][0]['input'] += ' changed'
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'conditions changed'):
                await app.improve('', preview_token=preview.preview_token)
            self.assertEqual(provider.calls, [])
