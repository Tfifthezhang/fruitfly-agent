"""External registration reaches actual isolated trials and subsequent generations."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import yaml

from fruitfly_agent.extensions import ExtensionContext
from fruitfly_agent.run.extensions import load_extensions, discover_extensions
from fruitfly_agent.run import RunApplicationFactory
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest
from fruitfly_agent.lab.improvement.api import WorkflowBindings
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.rsi import EvolutionEngine
from fruitfly_agent.rsi.contracts import VerificationEvidence
from fruitfly_agent.run.evolution import RunEvolutionHost
from tests.support.improvers import OfflineGenerator, FirstComposer, FirstSelector, SyntheticVerification
from tests.support.materials import _write_models
from tests.support.faux_provider import FauxProvider


class EchoGuidance(FauxProvider):
    def __call__(self, view, *, signal=None):
        self.respond_text(view.system_prompt)
        return super().__call__(view, signal=signal)


class DeveloperExtensionTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_interception_is_recreated_per_trial_without_live_state_leakage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_models(root)
            guidance = Path(__file__).resolve().parents[2] / 'examples/extensions/developer_guidance.py'
            hook = root / 'counter.py'
            hook.write_text('''def register(api):
    def apply(event, ctx):
        ctx.state['requests'] = ctx.state.get('requests', 0) + 1
        event.system_prompt += '\\nEXTENSION_REQUEST=' + str(ctx.state['requests'])
    api.intercept_agent('before_request', apply)
''')
            providers = Mock(); providers.create.side_effect = lambda *args: EchoGuidance()
            generators = GeneratorRegistry(); generators.register('offline-rule', OfflineGenerator)
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=providers,
                extensions=load_extensions((str(guidance), str(hook)), workspace=root),
                improvement_bindings=WorkflowBindings(generators=generators,
                    composer=lambda *args: FirstComposer(), selector=lambda *args: FirstSelector()))
            factory.configuration.set_mechanism('developer-guidance-owner', enabled=True)
            factory.configuration.save(); factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            self.addAsyncCleanup(app.close)
            first = await app.submit('ordinary request')
            self.assertIn('EXTENSION_REQUEST=1', first.messages[-1].text)
            request = WorkflowRequest('Compare task guidance.', component_ids=('developer-guidance',),
                generator_id='offline-rule', strategy_id='simple', retain_experience=False)
            preview = app.workflow_preview(request)
            await app.improve('', preview_token=preview.preview_token)
            records = factory._component_jobs.outcome.records
            self.assertEqual(len(records), 2)
            self.assertTrue(all('EXTENSION_REQUEST=1' in record.output for record in records))
            second = await app.submit('ordinary request after trials')
            self.assertIn('EXTENSION_REQUEST=2', second.messages[-1].text)

    async def test_late_owned_resources_close_in_reverse_order_even_after_failure(self):
        closed = []
        class Resource:
            def __init__(self, name, fail=False):
                self.name, self.fail = name, fail
            async def aclose(self):
                closed.append(self.name)
                if self.fail:
                    raise OSError('cleanup failed')
        context = ExtensionContext('resource-owner', own=lambda value: value)
        context.own(Resource('first'))
        context.own(Resource('second', True))
        with self.assertRaisesRegex(RuntimeError, 'cleanup'):
            await context.aclose()
        self.assertEqual(closed, ['second', 'first'])
        with self.assertRaisesRegex(RuntimeError, 'retired'):
            context.own(Resource('third'))

    async def test_reload_command_replaces_command_group_and_failure_retains_active_runtime(self):
        from fruitfly_agent.run.extensions.commands import bind_extension_commands
        from fruitfly_agent.interactive.terminal import TerminalCommandRegistry
        from fruitfly_agent.interactive.contracts.commands import InteractiveCommand
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_models(root)
            source = root / 'commands.py'
            def body(name):
                return ('from fruitfly_agent.interactive.contracts.commands import CommandResult\n'
                    'def register(api):\n    api.register_command('+repr(name)+', lambda command: CommandResult(text='+repr(name)+'))\n')
            source.write_text(body('alpha'))
            providers = Mock(); providers.create.side_effect = lambda *args: EchoGuidance()
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=providers,
                extensions=load_extensions((str(source),), workspace=root))
            factory.configuration.save(); factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            self.addAsyncCleanup(app.close)
            await app.submit('retain this conversation')
            registry = TerminalCommandRegistry()
            bind_extension_commands(registry, app, factory)
            self.assertEqual((await registry.execute(InteractiveCommand('alpha'))).text, 'alpha')
            initial = app.runtime_manifest['digest']
            source.write_text('raise ValueError("registration failed")')
            with self.assertRaisesRegex(ValueError, 'registration failed'):
                await registry.execute(InteractiveCommand('reload'))
            self.assertEqual(app.runtime_manifest['digest'], initial)
            self.assertEqual((await registry.execute(InteractiveCommand('alpha'))).text, 'alpha')
            source.write_text(body('bravo'))
            await registry.execute(InteractiveCommand('reload'))
            self.assertIsNone(await registry.execute(InteractiveCommand('alpha')))
            self.assertEqual((await registry.execute(InteractiveCommand('bravo'))).text, 'bravo')
            self.assertNotEqual(app.runtime_manifest['digest'], initial)
            self.assertEqual(app.status.message_count, 2)

    async def test_external_algorithm_runs_trials_activates_and_binds_two_generations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_models(root)
            source = Path(__file__).resolve().parents[2] / 'examples/extensions/developer_guidance.py'
            extensions = load_extensions((str(source),), workspace=root)
            providers = Mock()
            seen = []
            def create(*args):
                value = EchoGuidance()
                seen.append(value)
                return value
            providers.create.side_effect = create
            generators = GeneratorRegistry()
            generators.register('offline-rule', OfflineGenerator)
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=providers,
                extensions=extensions, improvement_bindings=WorkflowBindings(generators=generators,
                    composer=lambda *args: FirstComposer(), selector=lambda *args: FirstSelector(),
                    verifier=SyntheticVerification()))
            factory.configuration.set_mechanism('developer-guidance-owner', enabled=True)
            factory.configuration.save()
            config = root / '.fruitfly/config.yaml'
            raw = yaml.safe_load(config.read_text())
            raw['profiles']['default']['extensions'] = [str(source)]
            config.write_text(yaml.safe_dump(raw))
            factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            self.addAsyncCleanup(app.close)
            initial = app.runtime_manifest['digest']
            request = WorkflowRequest('Show applied guidance.', component_ids=('developer-guidance',),
                generator_id='offline-rule', scope='persistent', strategy_id='simple', retain_experience=False)
            async def verify(record, text):
                return VerificationEvidence(record.candidate_id, record.artifact_id,
                    record.parent_manifest_digest, 'synthetic-extension', True)
            host = RunEvolutionHost(app, factory, policy_id='synthetic-extension', verify=verify, request=request)
            result = await EvolutionEngine().evolve(host, job_id='external', policy_id='synthetic-extension',
                direction='Improve developer guidance.', max_steps=2)
            self.assertEqual((result.phase, result.steps), ('complete', 2))
            self.assertNotEqual(initial, app.runtime_manifest['digest'])
            reply = await app.submit('Use the active algorithm.')
            self.assertEqual(reply.messages[-1].text.count('Use exact answers.'), 2)
            prompts = [call['system_prompt'] for provider in seen for call in provider.calls]
            self.assertTrue(any(text.count('Use exact answers.') == 1 for text in prompts))
            self.assertEqual(app.runtime_manifest['harness']['extensions'][0]['source'], str(source))

    async def test_reload_replaces_observers_and_retires_old_context_without_losing_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_models(root)
            path = root / 'extension.py'
            def source(label):
                return 'def register(api):\n    api.observe_agent("before_request", lambda event, ctx: ctx.record({"label": '+repr(label)+'}))\n'
            path.write_text(source('first'))
            extensions = load_extensions((str(path),), workspace=root)
            provider = EchoGuidance()
            providers = Mock(); providers.create.return_value = provider
            factory = RunApplicationFactory(cwd=root, environment={}, extensions=extensions, provider_registry=providers)
            factory.configuration.save(); factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            self.addAsyncCleanup(app.close)
            await app.submit('first task')
            prior = app.status.message_count
            digest = app.runtime_manifest['digest']
            path.write_text(source('second'))
            with self.assertRaisesRegex(ValueError, 'source changed'):
                extensions.validate()
            replacement = factory.replacement_extensions()
            await app.replace_factory(replacement)
            self.assertEqual(app.status.message_count, prior)
            self.assertNotEqual(digest, app.runtime_manifest['digest'])
            await app.submit('second task')
            self.assertIn('first task', provider.calls[-1]['messages'][0].content)

    def test_discovery_does_not_execute_and_source_mutation_blocks_assembly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'broken.py'
            path.write_text('raise RuntimeError("not a discovery operation")')
            self.assertEqual(discover_extensions(root), (str(path.resolve()),))
            with self.assertRaisesRegex(RuntimeError, 'discovery'):
                load_extensions((str(path),), workspace=root)
            context = ExtensionContext('test')
            context.state['count'] = 1
            context.close()
            with self.assertRaisesRegex(RuntimeError, 'retired'):
                context.state
