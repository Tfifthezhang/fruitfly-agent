"""Termination facts distinguish limits, denied execution and normal completion."""
import tempfile
from pathlib import Path
import unittest
from dataclasses import replace

from fruitfly_agent.core.data_model.runtime import BeforeToolCallResult
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.data_model import AgentToolResult
from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_config, make_tool, run_loop


class LoopFactTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_exhaustion_is_recorded_without_changing_legacy_stop_semantics(self):
        provider = FauxProvider()
        tool, calls = make_tool()
        provider.respond_tool_call('count', {'value': 'executed'})
        provider.respond_tool_call('count', {'value': 'skipped'})
        with tempfile.TemporaryDirectory() as directory, Session(Path(directory) / 'session.jsonl') as session:
            result = await run_loop(make_config(provider, [tool], max_tool_calls_per_turn=1, session=session), 'work')
            ending = [r.payload['data'] for r in session.read_all() if r.payload.get('event') == 'end'][-1]
        self.assertEqual(result.stop_reason, 'stop')
        self.assertFalse(result.is_error)
        self.assertEqual(calls, [{'value': 'executed'}])
        self.assertEqual(result.diagnostics.termination_reason, 'tool_budget_exhausted')
        self.assertEqual((result.diagnostics.tool_requests, result.diagnostics.tool_attempts,
            result.diagnostics.tool_started, result.diagnostics.tool_budget_skipped), (2, 1, 1, 1))
        self.assertEqual(ending['diagnostics']['termination_reason'], 'tool_budget_exhausted')

    async def test_blocked_and_truncated_calls_are_not_reported_as_started_tools(self):
        provider = FauxProvider()
        tool, calls = make_tool()
        provider.respond_length_with_tool_call('count', {'value': 'truncated'})
        provider.respond_tool_call('count', {'value': 'blocked'})
        provider.respond_text('done')
        result = await run_loop(make_config(provider, [tool],
            before_tool_call=lambda _: BeforeToolCallResult(block=True)), 'work')
        self.assertEqual(calls, [])
        self.assertEqual(result.diagnostics.termination_reason, 'model_complete')
        self.assertEqual(result.diagnostics.tool_output_skipped, 1)
        self.assertEqual(result.diagnostics.tool_attempts, 1)
        self.assertEqual(result.diagnostics.tool_errors, 1)
        self.assertEqual(result.diagnostics.tool_started, 0)

    async def test_provider_failure_retains_diagnostics_without_runtime_budget_control(self):
        provider = FauxProvider()
        provider.respond_fatal('provider failed',diagnostics={'stage':'connect'})
        result = await run_loop(make_config(provider), 'work')
        self.assertTrue(result.is_error)
        self.assertEqual(result.diagnostics.termination_reason, 'provider_error')
        self.assertEqual(result.diagnostics.provider_failures, 1)

    async def test_tool_reported_errors_remain_errors_without_parsing_the_output(self):
        provider = FauxProvider()
        tool, _ = make_tool()
        tool = replace(tool, execute=lambda _: AgentToolResult.error('an operation failed'))
        provider.respond_tool_call('count', {'value': 'attempt'})
        provider.respond_text('done')
        result = await run_loop(make_config(provider, [tool]), 'work')
        self.assertTrue(result.messages[-2].is_error)
        self.assertEqual(result.diagnostics.tool_errors, 1)
        self.assertEqual(result.diagnostics.tool_started, 1)

    async def test_zero_turn_limit_is_not_normal_model_completion(self):
        provider = FauxProvider()
        result = await run_loop(make_config(provider, max_turns=0), 'work')
        self.assertEqual(result.diagnostics.termination_reason, 'turn_budget_exhausted')
        self.assertEqual(provider.calls, [])
