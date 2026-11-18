"""Request capacity follows the model window and effective output reserve."""
import unittest

from fruitfly_agent.core.context.budget import ContextBudget, InputMeasurement


class ContextBudgetTests(unittest.TestCase):
    def test_model_window_and_output_reserve_change_capacity(self):
        budget = ContextBudget()
        measured = InputMeasurement(150000, 'offline', 'heuristic', 'request', 131072, 15000)
        self.assertTrue(measured.fits(1048576))
        self.assertTrue(budget.fits(1048576, measured))
        self.assertFalse(budget.fits(256000, measured))
        self.assertEqual(1868928, budget.capacity(2000000, measured.output_reserve))
        self.assertEqual(1934464, budget.capacity(2000000, 65536))

    def test_margin_and_model_output_reserve_are_both_enforced(self):
        budget = ContextBudget()
        measured = InputMeasurement(8000, 'offline', 'heuristic', 'request', 2000, 1000)
        self.assertTrue(budget.fits(11000, measured))
        self.assertFalse(budget.fits(10999, measured))
        self.assertFalse(budget.fits(1000, InputMeasurement(0, 'offline', 'heuristic', 'request', 2000)))
        unknown = InputMeasurement(None, 'offline', 'unknown', 'request', 2000)
        self.assertFalse(budget.fits(11000, unknown))

    def test_invalid_configuration_is_rejected(self):
        for values in ((True, .5), (0, .5), (.5, .75),
                       (float('nan'), .5), (.75, True)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                ContextBudget(*values)


class BudgetAdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_measured_request_reaches_provider(self):
        from fruitfly_agent.core.config import AgentLoopConfig
        from fruitfly_agent.core.data_model import UserMessage
        from fruitfly_agent.core.loop import run_agent_loop
        from fruitfly_agent.lab.context_manager.measurement.budget import MeasurementService
        from tests.support.faux_provider import FauxProvider

        provider = FauxProvider()
        provider.respond_text('done')
        result = await run_agent_loop(
            AgentLoopConfig(provider, context_window=1000000, max_tokens=131072,
                            context_meter=MeasurementService()),
            [UserMessage('abcd ' * 100000)],
        )
        self.assertFalse(result.is_error, result.error_details)
        self.assertEqual(1, len(provider.calls))

    async def test_noop_failed_and_state_only_reducers_cannot_bypass_the_ceiling(self):
        from fruitfly_agent.core.config import AgentLoopConfig
        from fruitfly_agent.core.data_model import ContextDecision, UserMessage
        from fruitfly_agent.core.loop import run_agent_loop
        from fruitfly_agent.lab.context_manager.measurement.budget import MeasurementService
        from tests.support.faux_provider import FauxProvider
        class Reducer:
            def __init__(self, mode): self.mode, self.calls = mode, 0
            def estimate(self, snapshot): return 2000
            async def check_budget(self, snapshot):
                self.calls += 1
                if self.mode == 'failed': raise ValueError('offline reducer failure')
                if self.mode == 'none': return None
                return ContextDecision(state={'covered': 1}, mechanism_id='fixture', base_revision=snapshot.revision)
            async def react_to_overflow(self, snapshot, error): return None
        for mode in ('absent', 'none', 'failed', 'state'):
            with self.subTest(mode=mode):
                provider = FauxProvider(); provider.respond_text('must not be consumed')
                reducer = None if mode == 'absent' else Reducer(mode)
                config = AgentLoopConfig(provider, context_window=1152, max_tokens=128,
                    context_meter=MeasurementService())
                result = await run_agent_loop(config, [UserMessage('evidence ' * 2000)], context_pipeline=reducer)
                self.assertTrue(result.is_error)
                self.assertEqual('context_overflow', result.error_details['kind'])
                self.assertEqual([], provider.calls)
                if reducer is not None: self.assertLessEqual(reducer.calls, 2)

    async def test_compaction_hook_expansion_cannot_bypass_final_admission(self):
        from dataclasses import replace
        from fruitfly_agent.core.config import AgentLoopConfig
        from fruitfly_agent.core.data_model import ContextDecision, UserMessage
        from fruitfly_agent.core.extensions.hooks import HookRegistry, BEFORE_COMPACTION
        from fruitfly_agent.core.loop import run_agent_loop
        from fruitfly_agent.lab.context_manager.measurement.budget import MeasurementService
        from tests.support.faux_provider import FauxProvider
        class Reducer:
            def estimate(self, snapshot): return 2000
            async def check_budget(self, snapshot):
                return ContextDecision(messages=(UserMessage('short'),), mechanism_id='fixture')
            async def react_to_overflow(self, snapshot, error): return None
        hooks = HookRegistry()
        hooks.add(BEFORE_COMPACTION, lambda event: replace(event, messages=[UserMessage('expanded ' * 3000)]))
        provider = FauxProvider(); provider.respond_text('must not run')
        config = AgentLoopConfig(provider, hooks=hooks, context_window=1152, max_tokens=128,
            context_meter=MeasurementService())
        result = await run_agent_loop(config, [UserMessage('original ' * 2000)], context_pipeline=Reducer())
        self.assertTrue(result.is_error)
        self.assertEqual([], provider.calls)

    async def test_unknown_measurement_fails_before_provider_call(self):
        from fruitfly_agent.core.config import AgentLoopConfig
        from fruitfly_agent.core.data_model import UserMessage
        from fruitfly_agent.core.loop import run_agent_loop
        from tests.support.faux_provider import FauxProvider
        for meter in (None,):
            provider = FauxProvider()
            result = await run_agent_loop(AgentLoopConfig(provider, context_meter=meter), [UserMessage('task')])
            self.assertEqual('context_budget_exhausted', result.error_details['kind'])
            self.assertEqual([], provider.calls)

    async def test_late_budget_stop_preserves_completed_tools_and_usage(self):
        from dataclasses import replace
        from fruitfly_agent.core.config import AgentLoopConfig
        from fruitfly_agent.core.data_model import AgentToolResult, TextBlock, UserMessage
        from fruitfly_agent.core.loop import run_agent_loop
        from fruitfly_agent.lab.context_manager.measurement.budget import MeasurementService
        from tests.support.faux_provider import FauxProvider
        from tests.support.loop import make_tool
        provider = FauxProvider()
        provider.respond_tool_call('count', {'value': 'once'})
        provider.respond_text('must not be requested')
        effects = []
        async def execute(ctx):
            effects.append(ctx.args['value'])
            return AgentToolResult(content=[TextBlock('large evidence ' * 2000)])
        tool = replace(make_tool()[0], execute=execute)
        result = await run_agent_loop(AgentLoopConfig(provider, tools=(tool,),
            context_window=1152, max_tokens=128,
            context_meter=MeasurementService()), [UserMessage('Inspect once.')])
        self.assertTrue(result.is_error)
        self.assertEqual('context_overflow', result.error_details['kind'])
        self.assertEqual(['once'], effects)
        self.assertEqual(1, result.tool_call_count)
        self.assertEqual(1, result.diagnostics.tool_started)
        self.assertEqual(1, len(provider.calls))
        self.assertEqual((10, 5), (result.usage.input_tokens, result.usage.output_tokens))
