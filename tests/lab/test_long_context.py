"""One long autonomous turn must reduce complete tool batches; fake Providers only."""
from dataclasses import replace
import unittest
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock, UserMessage
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.lab.context_manager.measurement.budget import MeasurementService, MeasurementConfig
from fruitfly_agent.lab.context_manager.reduction import WorkingMemoryReducer, WorkingMemoryConfig
from fruitfly_agent.lab.context_manager.reduction.cut import valid_tool_links
from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_tool


class LongContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_eighty_batches_finish_with_smaller_valid_requests_and_original_facts(self):
        provider = FauxProvider(); auxiliary = FauxProvider()
        for i in range(80):
            provider.respond_tool_call('count', {'value': str(i)})
            auxiliary.respond_text('Task goal: finish all steps. Completed tools recorded; inspect history for evidence.')
        provider.respond_text('all steps complete')
        tool, _ = make_tool()
        async def log(ctx): return AgentToolResult(content=[TextBlock('middle evidence ' + ctx.args['value'] + 'x' * 3000)])
        tool = replace(tool, execute=log)
        meter = MeasurementService(MeasurementConfig(margin_tokens=0, margin_ratio=0))
        reducer = WorkingMemoryReducer(WorkingMemoryConfig(memory_tokens=128, auxiliary_max_tokens=128, update_every_messages=3), auxiliary)
        config = AgentLoopConfig(provider, tools=(tool,), context_window=4096, max_tokens=64,
            max_tool_calls_per_turn=100, context_meter=meter)
        result = await run_agent_loop(config, [UserMessage('Finish all steps and verify the result')], context_pipeline=reducer)
        self.assertFalse(result.is_error, result.error_details)
        self.assertEqual(80, result.tool_call_count)
        self.assertEqual(162, len(result.canonical_messages))
        self.assertGreater(len(auxiliary.calls), 10)
        self.assertLess(len(result.messages), len(result.canonical_messages))
        for call in provider.calls:
            self.assertTrue(valid_tool_links(call['messages']))
            self.assertTrue(any(isinstance(m, UserMessage) and m.content == 'Finish all steps and verify the result' for m in call['messages']))
            from fruitfly_agent.core.data_model import ProviderView
            measure = await meter.measure(ProviderView(call['system_prompt'], call['messages'], [tool], call['model'], call['max_tokens']), provider)
            self.assertTrue(measure.fits(config.context_window))

    async def test_signed_prefix_retains_projection_while_memory_updates(self):
        from fruitfly_agent.core.data_model import ContextSnapshot, ContextItem
        provider = FauxProvider()
        messages = (UserMessage('old' * 4000), UserMessage('current'))
        snapshot = ContextSnapshot(tuple(ContextItem(str(i), m) for i,m in enumerate(messages)),
            messages, '', (), 4096, 'fake', 64, 'budget', rebase_allowed=False)
        reducer = WorkingMemoryReducer(WorkingMemoryConfig(max_pages=64, update_every_messages=1), provider)
        for _ in range(64): provider.respond_text('bounded memory')
        decision = await reducer.check_budget(snapshot)
        self.assertIsNone(decision.messages)
        self.assertTrue(provider.calls)
