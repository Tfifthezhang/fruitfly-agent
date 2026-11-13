"""External registration reaches actual isolated trials and subsequent generations."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import yaml

from fruitfly_agent.extensions import ExtensionContext
from fruitfly_agent.run.extensions import load_extensions, discover_extensions
from tests.support.task_execution import TaskApplicationFixture as RunApplicationFactory
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.improvement.contracts.requests import WorkflowRequest
from fruitfly_agent.lab.improvement.api import StageBindings
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.rsi import EvolutionEngine
from fruitfly_agent.rsi.contracts import VerificationEvidence
from fruitfly_agent.run.evolution import RunEvolutionHost
from tests.support.improvers import OfflineGenerator, FirstSelector, SyntheticVerification
from tests.support.materials import _write_models
from tests.support.faux_provider import FauxProvider


class EchoGuidance(FauxProvider):
    def __call__(self, view, *, signal=None):
        self.respond_text(view.system_prompt)
        return super().__call__(view, signal=signal)


class DeveloperExtensionTests(unittest.IsolatedAsyncioTestCase):
    def test_evidence_selector_extension_uses_shared_binding_and_rejects_collisions(self):
        from fruitfly_agent.extensions.api import ExtensionAPI, ExtensionSet
        from fruitfly_agent.lab.improvement.evidence_selection import RepresentativeSelector, SelectionSettings
        api = ExtensionAPI('selection-extension')
        observed = []
        def factory(settings):
            observed.append(settings)
            return RepresentativeSelector(SelectionSettings(max_cases=2))
        api.register_evidence_selector(factory)
        with self.assertRaises(ValueError):
            api.register_evidence_selector(factory)
        extensions = ExtensionSet((api,), identities=({'source': 'fixture', 'sha256': 'fixture'},))
        bindings = extensions.bindings()
        selector = bindings.evidence_selector({'owned-policy': {}})
        self.assertEqual([{'owned-policy': {}}], observed)
        self.assertEqual(2, selector.settings.max_cases)
        with self.assertRaisesRegex(ValueError, 'collision'):
            extensions.bindings(StageBindings(evidence_selector=factory))
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            api.register_evidence_selector(factory)


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
