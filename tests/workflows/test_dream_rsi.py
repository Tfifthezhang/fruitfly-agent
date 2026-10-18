"""DreamRSI uses normal preview, I-version, review, activation and recovery."""
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest

from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.improvement.methods.tree_search.policy import ExplorationPolicy
from fruitfly_agent.lab.improvement.methods.tree_search.history import DiscoveryNode, DiscoveryWorld, save_world
from fruitfly_agent.lab.improvement.methods.tree_search.improver import conditions
from tests.support.improvers import offline_factory
from tests.support.task_packs import install


class DreamWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def prepare(self, factory, root):
        suite = factory._current_improver.task_source.freeze('project', 'base_prompt')
        problem = SimpleNamespace(direction='Improve task performance.', cases_digest=suite.digest, task_execution_id=suite.execution_id,
            train=suite.train, validation=suite.validation, baseline=factory._current_targets['base_prompt'].snapshot(), policy=SimpleNamespace(policy_id=suite.policy_id))
        identity = conditions(problem, factory._current_runtime_config.model)
        return save_world(root, '.fruitfly/improvement/discovery', DiscoveryWorld(identity, (
            DiscoveryNode('n0', 'root', 0, 'one', .2), DiscoveryNode('n1', 'root', 1, 'two', .3),
            DiscoveryNode('n2', 'n0', 2, 'three', 1.))))

    async def test_policy_is_confirmed_activated_and_used_by_next_search(self):
        await self.check_policy_flow()

    async def test_unconfigured_policy_is_confirmed_activated_and_recovered(self):
        await self.check_policy_flow(unconfigured=True)

    async def check_policy_flow(self, *, unconfigured=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            factory = offline_factory(root, 'tree-search')
            pack = install(root)
            factory.configuration.set_parameter('tree-search', 'cases_path', str(pack.relative_to(root)))
            if unconfigured:
                factory.configuration.set_mechanism('tree-search', enabled=False)
            factory.configuration.save()
            factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            try:
                self.prepare(factory, root)
                before = factory.system_version()
                method = next(m for m in app.improvement_methods('I', 'tree-search.exploration-policy') if m.method_id == 'dream-rsi')
                self.assertTrue(method.available)
                material = next(p for p in app.task_packs_for_target('tree-search.exploration-policy')
                                if p.pack_id == 'project')
                self.assertEqual(material.error, '')
                self.assertEqual(method.task_sources, ('saved',))
                preview = app.improvement_preview(direction='Improve exploration', method_id='dream-rsi', pack_id='project',
                    target_id='tree-search.exploration-policy', parameters={'policy_revisions': 1,
                        'rounds': 2, 'workers': 1, 'discovery_calls': 2})
                provider = factory._current_runtime_config.provider
                self.assertEqual(provider.calls, [])
                candidate = ExplorationPolicy(root_every=100, stop_fraction=.5)
                provider.respond_text(candidate.serialize())
                for index, answer in enumerate(('wrong', 'wrong', 'B')):
                    provider.respond_text('{"text":"candidate instructions"}')
                    provider.respond_text('A')
                    provider.respond_text(answer)
                    if index == 1:
                        provider.respond_text('wrong')  # Baseline policy's final holdout result.
                    if index == 2:
                        provider.respond_text('SECRET_ANSWER')
                records = await app.start_improvement('Improve exploration', preview_token=preview.preview_token)
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0].role, 'I')
                self.assertEqual(factory.system_version(), before)
                await app.adopt_candidate(records[0].candidate_id)
                after = factory.system_version()
                self.assertEqual((after.harness, after.state), (before.harness, before.state))
                self.assertNotEqual(after.improver, before.improver)
                self.assertEqual(factory.select_improvement_method(method_id='tree-search', target_id='base_prompt').strategy.policy, candidate)
                active_provider = factory._current_runtime_config.provider
                active_provider.respond_text('wrong')
                for index in range(4):
                    active_provider.respond_text(json.dumps({'text': f'next candidate {index}'}))
                    active_provider.respond_text('A')
                    active_provider.respond_text('B')
                next_preview = app.improvement_preview(direction='Improve task performance.',
                    method_id='tree-search', target_id='base_prompt', pack_id='project')
                next_records = await app.improve('Improve task performance.', preview_token=next_preview.preview_token)
                self.assertEqual(next_records[0].role, 'H')
                trace = json.loads((root / dict(next_records[0].evidence)['Discovery history']).read_text())
                self.assertEqual([node['parent'] for node in trace['nodes']], ['root', 'n0', 'n1', 'n2'])
                active_provider.respond_text('done')
                await app.submit('Continue')
                path = Path(app.status.session_path)
            finally:
                await app.close()
            restored = AgentApplication(factory)
            await restored.start(resume=True, session_path=path)
            self.assertEqual(factory.select_improvement_method(method_id='tree-search', target_id='base_prompt').strategy.policy, candidate)
            await restored.close()

    async def test_missing_and_modified_histories_reject_before_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            factory = offline_factory(root, 'tree-search')
            pack = install(root)
            factory.configuration.set_parameter('tree-search', 'cases_path', str(pack.relative_to(root)))
            factory.configuration.save()
            factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            try:
                selection = dict(pack_id='project', method_id='dream-rsi', target_id='tree-search.exploration-policy', direction='Improve')
                with self.assertRaisesRegex(ValueError, 'histories'):
                    app.improvement_preview(**selection)
                history = self.prepare(factory, root)
                preview = app.improvement_preview(**selection)
                file = root / history
                file.write_text(file.read_text() + ' ')
                with self.assertRaisesRegex(ValueError, 'method changed'):
                    await app.improve('Improve', preview_token=preview.preview_token)
                self.assertEqual(factory._current_runtime_config.provider.calls, [])
            finally:
                await app.close()

    async def test_holdout_regression_never_publishes_a_policy_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            factory = offline_factory(root, 'tree-search')
            install(root)
            app = AgentApplication(factory)
            await app.start()
            try:
                self.prepare(factory, root)
                initial = factory.system_version()
                preview = app.improvement_preview(pack_id='project', direction='Improve', method_id='dream-rsi',
                    target_id='tree-search.exploration-policy', parameters={'policy_revisions': 1,
                        'rounds': 2, 'workers': 1, 'discovery_calls': 2})
                provider = factory._current_runtime_config.provider
                provider.respond_text(ExplorationPolicy(root_every=100, stop_fraction=.5).serialize())
                for index in range(3):
                    provider.respond_text(json.dumps({'text': f'candidate {index}'}))
                    provider.respond_text('A')
                    provider.respond_text('B')
                    if index == 1:
                        provider.respond_text('SECRET_ANSWER')
                    if index == 2:
                        provider.respond_text('wrong')
                self.assertEqual(await app.improve('Improve', preview_token=preview.preview_token), ())
                self.assertEqual(factory.system_version(), initial)
                for call in provider.calls:
                    if call['system_prompt'].startswith(('Improve a prefix-only', 'Propose one improved')):
                        self.assertNotIn('UNSEEN_INPUT', repr(call['messages']))
                        self.assertNotIn('SECRET_ANSWER', repr(call['messages']))
            finally:
                await app.close()

    async def test_exhausted_confirmation_budget_cannot_create_a_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            factory = offline_factory(root, 'tree-search')
            install(root)
            app = AgentApplication(factory)
            await app.start()
            try:
                self.prepare(factory, root)
                preview = app.improvement_preview(pack_id='project', direction='Improve', method_id='dream-rsi',
                    target_id='tree-search.exploration-policy', parameters={'policy_revisions': 1,
                        'max_metric_calls': 1, 'workers': 1})
                provider = factory._current_runtime_config.provider
                provider.respond_text(ExplorationPolicy(root_every=100, stop_fraction=.5).serialize())
                provider.respond_text('{"text":"candidate"}')
                provider.respond_text('A')
                self.assertEqual(await app.improve('Improve', preview_token=preview.preview_token), ())
                self.assertEqual(app.candidates(), ())
                self.assertEqual(len(provider.calls), 3)
            finally:
                await app.close()

    async def test_cancellation_closes_policy_request_without_activation(self):
        import asyncio
        from fruitfly_agent.core.model_stream import AssistantMessageEventStream
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            factory = offline_factory(root, 'tree-search')
            install(root)
            app = AgentApplication(factory)
            await app.start()
            try:
                self.prepare(factory, root)
                initial = factory.system_version()
                preview = app.improvement_preview(pack_id='project', direction='Improve', method_id='dream-rsi',
                    target_id='tree-search.exploration-policy')
                entered, cleaned = asyncio.Event(), asyncio.Event()
                async def blocked():
                    entered.set()
                    try:
                        await asyncio.Event().wait()
                    finally:
                        cleaned.set()
                    yield
                factory._current_runtime_config.provider.script.append(
                    lambda *args, **kwargs: AssistantMessageEventStream(blocked()))
                task = app.start_improvement('Improve', preview_token=preview.preview_token)
                await asyncio.wait_for(entered.wait(), 5)
                app.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertTrue(cleaned.is_set())
                self.assertEqual(app.candidates(), ())
                self.assertEqual(factory.system_version(), initial)
            finally:
                await app.close()
