"""Admission of child execution identities and explicit task inputs."""
import unittest

from fruitfly_agent.lab.agents.subagent.contracts import ChildRequest, ExecutionIdentity


class ChildAdmissionTests(unittest.TestCase):
    def test_identity_rejects_paths_and_unbounded_values(self):
        for value in ('', '../child', 'child/name', 'child\\name', 'x' * 129, 'child\n', 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ExecutionIdentity('scope', value, 'run')

    def test_request_preserves_task_and_requires_explicit_identity(self):
        identity = ExecutionIdentity('scope', 'agent-1', 'run_1')
        request = ChildRequest(identity, 'Inspect exports', 'Read only')
        self.assertEqual(request.identity, identity)
        self.assertEqual(request.task, 'Inspect exports')
        for task, context in (('', ''), ('  ', ''), (1, ''), ('Inspect', None)):
            with self.subTest(task=task, context=context), self.assertRaises(ValueError):
                ChildRequest(identity, task, context)
        with self.assertRaises(ValueError):
            ChildRequest(None, 'Inspect')


class ChildCoreExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_child_request_limit_stops_a_tool_loop_and_retires_resources(self):
        import tempfile
        from dataclasses import replace
        from fruitfly_agent.core.tool_runtime import AgentTool
        from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
        from tests.support.subagents import ChildFixture
        with tempfile.TemporaryDirectory() as directory:
            fixture = ChildFixture(directory)
            def provider(request):
                p = fixture.answer()
                p.script.clear()
                for _ in range(5): p.respond_tool_call('inspect', {})
                return p
            fixture.provider = provider
            async def inspect(ctx): return AgentToolResult([TextBlock('observed')])
            tool = AgentTool('inspect', 'Inspect', 'Read', {'type': 'object'}, inspect)
            async def prepare(request):
                runtime = await fixture.prepare(request)
                return replace(runtime, config=replace(runtime.config, tools=(tool,)))
            service = fixture.service(max_model_requests=2)
            service.prepare = prepare
            try:
                service.begin()
                row = service.spawn('Inspect')
                value = await service.wait([(row['agent_id'], row['run_id'])], timeout_seconds=1)
                self.assertEqual('failed', value['executions'][0]['state'])
                self.assertEqual(2, len(fixture.providers[0].calls))
                self.assertEqual(1, fixture.closed)
            finally:
                await service.close()

    async def test_running_child_receives_steering_at_the_next_request_once(self):
        import asyncio
        import tempfile
        from dataclasses import replace
        from fruitfly_agent.core.tool_runtime import AgentTool
        from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
        from tests.support.subagents import ChildFixture
        with tempfile.TemporaryDirectory() as directory:
            fixture = ChildFixture(directory)
            gate, entered = asyncio.Event(), asyncio.Event()
            def provider(request):
                p = fixture.answer(); p.script.clear()
                p.respond_tool_call('inspect', {}); p.respond_text('done')
                return p
            fixture.provider = provider
            async def inspect(ctx):
                entered.set(); await gate.wait()
                return AgentToolResult([TextBlock('observed')])
            tool = AgentTool('inspect', 'Inspect', 'Read', {'type': 'object'}, inspect)
            async def prepare(request):
                runtime = await fixture.prepare(request)
                return replace(runtime, config=replace(runtime.config, tools=(tool,)))
            service = fixture.service(); service.prepare = prepare
            try:
                service.begin()
                row = service.spawn('Inspect')
                await asyncio.wait_for(entered.wait(), 1)
                accepted = service.send(row['agent_id'], row['run_id'], 'steer', 'Keep counterexamples')
                self.assertTrue(accepted['accepted'])
                gate.set()
                await service.wait([(row['agent_id'], row['run_id'])], timeout_seconds=1)
                messages = fixture.providers[0].calls[1]['messages']
                self.assertEqual(1, sum('Keep counterexamples' in str(m.to_dict()) for m in messages))
            finally:
                await service.close()
