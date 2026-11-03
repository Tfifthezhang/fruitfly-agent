"""Operation facts survive cancellation and preserve concurrent interval semantics."""
import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.core.observation import ObservationContext, bind_observation, operation
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.session.observations import read_observations, summarize_observations
from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_config, run_loop


class ObservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_loop_records_stages_and_tool_failure_without_source_content(self):
        from tests.support.loop import make_tool
        from fruitfly_agent.core.data_model import AgentToolResult
        provider = FauxProvider()
        provider.respond_tool_call('count', {'value': 'private argument'})
        provider.respond_text('answer')
        tool, _ = make_tool()
        tool = replace(tool, execute=lambda _: AgentToolResult.error('private result'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'session.jsonl'
            with Session(path) as session:
                result = await run_loop(make_config(provider, [tool], session=session), 'private prompt')
                self.assertFalse(result.is_error)
            events = read_observations(path)
            summary = summarize_observations(events)
        stages = summary['stages']
        for stage in ('agent.run', 'request.prepare', 'model.request', 'tool.authorize', 'tool.execute'):
            self.assertIn(stage, stages)
        self.assertEqual(1, stages['tool.execute']['failed'])
        self.assertFalse(summary['unfinished'])
        self.assertNotIn('private', str([event.to_dict() for event in events]))
        self.assertEqual(1, len({event.run_id for event in events}))

    async def test_parent_context_is_task_local_and_cancelled_work_is_not_success(self):
        events = []
        async def child():
            with operation('child'):
                raise asyncio.CancelledError
        with bind_observation(ObservationContext(sink=events.append, run_id='run')):
            with operation('parent'):
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.create_task(child())
        parent, child_start, child_end, parent_end = events
        self.assertEqual(parent.operation_id, child_start.parent_operation_id)
        self.assertEqual('cancelled', child_end.state)
        self.assertEqual('succeeded', parent_end.state)

    async def test_observer_failure_does_not_change_run(self):
        provider = FauxProvider(); provider.respond_text('answer')
        def broken(event):
            raise RuntimeError('observer unavailable')
        with self.assertLogs('fruitfly_agent.core.observation.scope', level='WARNING'):
            result = await run_loop(make_config(provider, on_observation=broken), 'question')
        self.assertFalse(result.is_error)

    def test_summary_uses_interval_union_and_retains_unfinished_unknown(self):
        events = []
        with bind_observation(ObservationContext(sink=events.append, run_id='run')):
            with operation('one'):
                pass
        begin, end = events
        one = replace(end, started_monotonic=10., elapsed_seconds=5.)
        two = replace(end, operation_id='second', started_monotonic=12., elapsed_seconds=5.)
        unfinished = replace(begin, operation_id='unfinished')
        result = summarize_observations([one, two, unfinished])
        self.assertEqual(7., result['observed_wall_seconds'])
        self.assertEqual(10., result['stages']['one']['operation_seconds'])
        self.assertIsNone(result['unfinished'][0]['elapsed_seconds'])

    def test_failure_round_trip_preserves_bounded_structural_causes(self):
        import json
        from fruitfly_agent.core.observation import FailureCause, FailureInfo
        failure = FailureInfo('provider', 'stream', 'response_parse', 'exception_type',
            causes=(FailureCause('JSONDecodeError', 'response_parse'),), http_status=200)
        self.assertEqual(failure, FailureInfo.from_dict(json.loads(json.dumps(failure.to_dict()))))
        with self.assertRaises(ValueError):
            FailureInfo('provider', 'stream', causes=(FailureCause('ValueError'),) * 7)
        with self.assertRaises(ValueError):
            FailureInfo('provider', 'stream', http_status=True)

    async def test_untrusted_tool_ids_cannot_break_passive_observation(self):
        from tests.support.loop import make_tool
        from fruitfly_agent.core.data_model import AssistantMessage, ToolCallBlock
        provider = FauxProvider()
        provider.respond(AssistantMessage([ToolCallBlock('invalid correlation ' * 100, 'count', {})], stop_reason='toolUse'))
        provider.respond_text('answer')
        tool, _ = make_tool()
        events = []
        result = await run_loop(make_config(provider, [tool], on_observation=events.append), 'question')
        self.assertFalse(result.is_error)
        calls = [event for event in events if event.stage == 'tool.call']
        self.assertTrue(calls)
        self.assertTrue(all(event.tool_call_id.startswith('opaque-') for event in calls))
