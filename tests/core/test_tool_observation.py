"""Result observation is isolated and covers non-executed tool calls."""

import unittest
from fruitfly_agent.core.data_model import AssistantMessage, ToolCallBlock
from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_config, make_tool, run_loop


class ToolObservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_observer_receives_copies_and_preserves_success_hooks(self):
        tool, _ = make_tool()
        provider = FauxProvider()
        provider.respond_tool_call('count', {'value': 'one'})
        provider.respond_text('done')
        observed, rewritten = [], []
        def after(ctx, result):
            rewritten.append(ctx.tool_call_id)
            return result
        def observe(name, result, cancelled):
            observed.append((name, result.is_error, cancelled))
            result.content.clear()
            raise RuntimeError('observer failed')
        result = await run_loop(make_config(provider, [tool], after_tool_call=after, on_tool_result=observe), 'go')
        self.assertEqual(observed, [('count', False, False)])
        self.assertEqual(rewritten, ['call_1'])
        self.assertEqual(result.messages[-2].content[0].text, 'count ok')

    async def test_budget_rejection_and_unknown_tools_are_observed_once(self):
        tool, calls = make_tool()
        provider = FauxProvider()
        provider.respond(AssistantMessage(content=[ToolCallBlock('missing', 'unknown', {}),
            ToolCallBlock('budget', 'count', {'value': 'two'})], stop_reason='toolUse'))
        provider.respond_text('done')
        observed = []
        result = await run_loop(make_config(provider, [tool], max_tool_calls_per_turn=1,
            on_tool_result=lambda name, result, cancelled: observed.append((name, result, cancelled))), 'go')
        self.assertEqual([row[1].tool_call_id for row in observed], ['missing', 'budget'])
        self.assertTrue(all(row[1].is_error for row in observed))
        self.assertEqual(calls, [])
        self.assertFalse(result.is_error)
