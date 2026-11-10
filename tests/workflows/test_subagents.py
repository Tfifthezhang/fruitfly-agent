"""Daily Application delegation remains configurable and visible through public ports."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.interactive.terminal.bindings import TerminalBindings
from fruitfly_agent.interactive.terminal.features.subagent import subagent_handler
from fruitfly_agent.interactive.interaction.commands import parse_command
from tests.support.faux_provider import FauxProvider
from tests.support.materials import _write_models

class SubagentWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_switch_exposes_group_and_command_follows_runtime_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_models(root, context_window=32000)
            registry = Mock()
            providers = []
            def create(*args):
                p = FauxProvider(); providers.append(p); return p
            registry.create.side_effect = create
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=registry, retained_state_enabled=False)
            factory.configuration.set_mechanism('subagent', enabled=True)
            self.assertTrue(factory.configuration.save().saved)
            factory.reload_configuration()
            app = AgentApplication(factory)
            try:
                await app.start()
                parent = providers[0]
                parent.respond_tool_call('subagent_spawn', {'task': 'Inspect public exports'})
                parent.respond_text('provisional')
                parent.respond_text('integrated result')
                def children(*args):
                    p = FauxProvider(); p.respond_text('child finding'); return p
                registry.create.side_effect = children
                result = await app.submit('Inspect independently')
                self.assertFalse(result.is_error, result.error_details)
                self.assertEqual('integrated result', result.messages[-1].text)
                self.assertEqual(5, len([name for name in app.status.tool_names if name.startswith('subagent_')]))
                monitor = app.subagents
                self.assertEqual('completed', monitor.snapshot().executions[0].state)
                bindings = TerminalBindings.from_session(app)
                command = subagent_handler(bindings.subagents)
                self.assertIn('completed', command(parse_command('/subagent')).text)
                factory.configuration.set_mechanism('subagent', enabled=False)
                await app.apply_configuration()
                self.assertIsNone(app.subagents)
                self.assertNotIn('subagent_spawn', app.status.tool_names)
                self.assertIn('disabled', command(parse_command('/subagent')).text)
                factory.configuration.set_mechanism('subagent', enabled=True)
                await app.apply_configuration()
                self.assertEqual('completed', app.subagents.snapshot().executions[0].state)
            finally:
                await app.close()

    async def test_running_monitor_and_parent_cancel_retire_the_child_before_return(self):
        import io
        from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
        from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
        from fruitfly_agent.interactive.terminal import TerminalFrontend
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_models(root, context_window=32000)
            registry = Mock()
            providers = []
            def create(*args):
                provider = FauxProvider(); providers.append(provider); return provider
            registry.create.side_effect = create
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=registry, retained_state_enabled=False)
            factory.configuration.set_mechanism('subagent', enabled=True)
            self.assertTrue(factory.configuration.save().saved)
            factory.reload_configuration()
            app = AgentApplication(factory)
            entered, retired = asyncio.Event(), asyncio.Event()
            try:
                await app.start()
                providers[0].respond_tool_call('subagent_spawn', {'task': 'Wait independently'})
                providers[0].respond_text('provisional')
                def child(*args):
                    provider = FauxProvider()
                    async def events():
                        entered.set()
                        try:
                            await asyncio.Event().wait()
                            yield StreamDone(AssistantMessage([TextBlock('unreachable')], 'stop'))
                        finally:
                            retired.set()
                    provider.script.append(lambda view, signal=None: AssistantMessageEventStream(events()))
                    return provider
                registry.create.side_effect = child
                task = asyncio.create_task(app.submit('Delegate'))
                await asyncio.wait_for(entered.wait(), 2)
                self.assertTrue(app.running)
                frontend = TerminalFrontend(app, input_stream=io.StringIO(), output_stream=io.StringIO())
                status = await frontend.commands.execute(parse_command('/subagent'))
                self.assertIn('running', status.text)
                self.assertEqual(1, app.subagents.snapshot().executions[0].model_requests)
                self.assertTrue(app.cancel())
                result = await asyncio.wait_for(task, 2)
                self.assertEqual('aborted', result.stop_reason)
                self.assertTrue(retired.is_set())
                row = app.subagents.snapshot().executions[0]
                self.assertEqual(('cancelled', 'confirmed'), (row.state, row.cleanup))
            finally:
                await app.close()
