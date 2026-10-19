"""Tool-owned descriptions and actual outcomes reach every frontend offline."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import io
import unittest

from fruitfly_agent.core.config import AgentLoopConfig, ToolExecutionConfig
from fruitfly_agent.core.data_model import AgentToolResult, AssistantMessage, TextBlock, ToolCallBlock
from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.core.tool_runtime.authorization import AuthorizationDecision
from fruitfly_agent.interactive import InteractiveSession, TerminalFrontend, TerminalRenderer
from fruitfly_agent.interactive.contracts.commands import InteractiveCommand
from fruitfly_agent.interactive.contracts.events import ToolStarted, ToolFinished, ToolOutput, event_from_dict
from fruitfly_agent.lab.tools.bash import create_bash_tool
from tests.support.faux_provider import FauxProvider
from tests.support.terminal import ScriptedLines, run_finished


class ToolPresentationTests(unittest.IsolatedAsyncioTestCase):
    def tool(self, execute=None, **kwargs):
        return AgentTool('custom', 'Inspect resource', 'Model instructions',
            {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']},
            execute or (lambda ctx: AgentToolResult(content=[TextBlock(ctx.args['path'])])), **kwargs)

    async def submit(self, tool, args=None, **config):
        provider = FauxProvider()
        provider.respond_tool_call(tool.name, {'path': 'README.md'} if args is None else args)
        provider.respond_text('done')
        events = []
        session = InteractiveSession(AgentLoopConfig(provider=provider, tools=(tool,), **config), event_sink=events.append)
        result = await session.submit('inspect')
        return session, events, result

    async def test_custom_tool_description_is_isolated_and_round_trips_without_renderer_registration(self):
        def describe(args):
            path = args['path']
            args['path'] = 'mutated'
            return 'Inspect ' + path
        session, events, result = await self.submit(self.tool(describe_call=describe))
        started = next(e for e in events if isinstance(e, ToolStarted))
        finished = next(e for e in events if isinstance(e, ToolFinished))
        self.assertEqual(started.description, 'Inspect README.md')
        self.assertEqual(finished.description, started.description)
        self.assertEqual(started.arguments['path'], 'README.md')
        self.assertEqual(finished.output, 'README.md')
        self.assertEqual(finished.status, 'succeeded')
        self.assertGreaterEqual(finished.elapsed_seconds, 0)
        self.assertEqual(event_from_dict(finished.to_dict()), finished)
        output = io.StringIO()
        renderer = TerminalRenderer(output)
        await renderer.render(started)
        await renderer.render(finished)
        await renderer.close()
        self.assertIn('◐ Inspect README.md', output.getvalue())
        self.assertIn('✓ Inspect README.md · Completed', output.getvalue())
        self.assertNotIn('Model instructions', output.getvalue())

    async def test_missing_empty_invalid_and_broken_describers_fall_back_to_label(self):
        def broken(args):
            raise ValueError('bad metadata')
        for describe in (None, lambda args: '', lambda args: None, broken):
            with self.subTest(describe=describe):
                _, events, result = await self.submit(self.tool(describe_call=describe))
                self.assertFalse(result.is_error)
                self.assertEqual(next(e.description for e in events if isinstance(e, ToolStarted)), 'Inspect resource')

    async def test_errors_validation_and_permission_denial_have_failed_results(self):
        def fail(ctx):
            raise RuntimeError('offline failure')
        class Deny:
            @asynccontextmanager
            async def authorize(self, request, *, signal=None):
                yield AuthorizationDecision(False, 'offline denial')
        for tool, args, config in ((self.tool(execute=fail), None, {}),
                                   (self.tool(), {}, {}),
                                   (self.tool(), None, {'tool_authorizer': Deny()})):
            with self.subTest(config=config, args=args):
                _, events, _ = await self.submit(tool, args, **config)
                finishes = [e for e in events if isinstance(e, ToolFinished)]
                self.assertEqual(len(finishes), 1)
                self.assertEqual(finishes[0].status, 'failed')
                self.assertTrue(finishes[0].output)

    async def test_parallel_cancellation_preserves_completed_results_and_call_identity(self):
        entered = asyncio.Event()
        async def slow(ctx):
            entered.set()
            await asyncio.Event().wait()
        provider = FauxProvider()
        provider.respond(AssistantMessage(content=[ToolCallBlock('fast', 'custom', {'path':'ok'}),
            ToolCallBlock('slow', 'slow', {'path':'wait'}), ToolCallBlock('queued', 'slow', {'path':'later'})], stop_reason='toolUse'))
        events = []
        session = InteractiveSession(AgentLoopConfig(provider=provider,
            tools=(self.tool(), replace(self.tool(execute=slow), name='slow', label='Wait for resource')),
            tool_execution=ToolExecutionConfig(max_parallel=2)), event_sink=events.append)
        task = asyncio.create_task(session.submit('run'))
        await asyncio.wait_for(entered.wait(), 1)
        session.cancel()
        result = await asyncio.wait_for(task, 2)
        self.assertEqual(result.stop_reason, 'aborted')
        finished = {e.tool_call_id: e for e in events if isinstance(e, ToolFinished)}
        self.assertEqual({key:e.status for key,e in finished.items()},
            {'fast':'succeeded', 'slow':'cancelled', 'queued':'cancelled'})
        self.assertEqual(finished['fast'].description, 'Inspect resource')
        self.assertEqual(finished['slow'].description, 'Wait for resource')
        self.assertIn('effects may have occurred', finished['slow'].output)

    async def test_bash_description_is_optional_and_does_not_change_execution(self):
        tool = create_bash_tool()
        for args, expected in (({'command':'unused'}, 'Execute shell command'),
                               ({'command':'unused', 'description':'Run menu tests'}, 'Run menu tests')):
            with self.subTest(args=args):
                observed = []
                tool = replace(tool, execute=lambda ctx: observed.append(dict(ctx.args)) or AgentToolResult(content=[]))
                _, events, _ = await self.submit(tool, args)
                self.assertEqual(next(e.description for e in events if isinstance(e, ToolStarted)), expected)
                self.assertEqual(observed, [args])

    async def test_legacy_event_is_unknown_and_terminal_control_sequences_are_escaped(self):
        legacy = event_from_dict(dict(type='tool_finished', run_id='r', tool_call_id='c',
            tool_name='custom', output='output', terminate=False))
        self.assertEqual(legacy.status, 'unknown')
        output = io.StringIO()
        renderer = TerminalRenderer(output)
        await renderer.render(replace(legacy, description='Inspect\x1b[2J resource', output='bad\x1b[2J output'))
        await renderer.close()
        self.assertIn('Finished', output.getvalue())
        self.assertNotIn('Completed', output.getvalue())
        self.assertNotIn('\x1b', output.getvalue())

    async def test_parallel_starts_cannot_reset_live_output_bounds(self):
        output = io.StringIO()
        renderer = TerminalRenderer(output)
        await renderer.render(ToolStarted(run_id='r', tool_call_id='first', tool_name='custom', arguments={}))
        await renderer.render(ToolOutput(run_id='r', text='x' * 600))
        await renderer.render(ToolStarted(run_id='r', tool_call_id='second', tool_name='custom', arguments={}))
        await renderer.render(ToolOutput(run_id='r', text='y' * 600))
        await renderer.close()
        self.assertEqual(output.getvalue().count('x'), 600)
        self.assertEqual(output.getvalue().count('y'), 200)
        self.assertIn('live tool output truncated', output.getvalue())

    async def test_escaped_live_output_is_bounded_and_result_status_is_explicit(self):
        output = io.StringIO()
        renderer = TerminalRenderer(output, tool_output_limit=12)
        await renderer.render(ToolOutput(run_id='r', text='\x1b' * 10))
        self.assertEqual(output.getvalue().count('\\x1b'), 3)
        self.assertIn('live tool output truncated', output.getvalue())
        for status, label in (('succeeded', 'Completed'), ('failed', 'Failed'), ('cancelled', 'Cancelled')):
            await renderer.render(ToolFinished(run_id='r', tool_call_id=status, tool_name='custom',
                description='Inspect resource', status=status, output='observed result', terminate=False))
            self.assertIn('Inspect resource · ' + label, output.getvalue())
        await renderer.close()

    async def test_details_command_uses_retained_results_without_extra_model_calls(self):
        body = 'retained output\n' * 100
        session, events, _ = await self.submit(self.tool(execute=lambda ctx: AgentToolResult(content=[TextBlock(body)])))
        output = io.StringIO()
        frontend = TerminalFrontend(session, output_stream=output, input_stream=io.StringIO(),
            line_editor=ScriptedLines('/tools', '/tools call_1', '/tools missing', '/exit'))
        await frontend.run()
        self.assertIn('call_1 · Inspect resource · succeeded', output.getvalue())
        self.assertIn(body, output.getvalue())
        self.assertIn('unavailable in the retained event window', output.getvalue())
        self.assertEqual(len([e for e in session.trace(200) if isinstance(e, ToolFinished)]), 1)


if __name__ == '__main__':
    unittest.main()
