"""Fault injection for component isolation and bounded recovery.

Verify callback defaults, structured Provider failures, tool errors,
recovery limits, and task cancellation propagation.
"""

from __future__ import annotations

import asyncio
import unittest

from fruitfly_agent.core.model_stream import AssistantMessageEventStream, TextDelta
from fruitfly_agent.core.data_model import AgentToolResult, ContextDecision, TextBlock
from fruitfly_agent.core.extensions.hooks import BEFORE_RUN, HookRegistry

from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_config, make_tool, run_loop


class _SyncRaisingProvider:
    def __call__(self, view, *, signal=None):
        raise TypeError("sync provider boom")


class _MidStreamRaisingProvider:
    def __call__(self, view, *, signal=None):
        async def gen():
            yield TextDelta(text="partial")
            raise RuntimeError("mid-stream boom")

        return AssistantMessageEventStream(gen())


class _CheckBudgetRaisingCompactor:
    def estimate(self, ctx):
        return 0

    async def check_budget(self, ctx):
        raise RuntimeError("budget boom")

    async def react_to_overflow(self, ctx, error):
        return None


class _EstimateRaisingCompactor:
    def __init__(self):
        self.react_calls = 0

    def estimate(self, ctx):
        raise RuntimeError("estimate boom")

    async def check_budget(self, ctx):
        return None

    async def react_to_overflow(self, ctx, error):
        self.react_calls += 1
        return ContextDecision(messages=ctx.messages, retry=True, mechanism_id="test")


class _ReactRaisingCompactor:
    def estimate(self, ctx):
        return 0

    async def check_budget(self, ctx):
        return None

    async def react_to_overflow(self, ctx, error):
        raise RuntimeError("react boom")


class _EndlessRecoveryCompactor:
    def estimate(self, ctx):
        return 0

    async def check_budget(self, ctx):
        return None

    async def react_to_overflow(self, ctx, error):
        return ContextDecision(messages=ctx.messages, retry=True, mechanism_id="endless")


class _RecordingRecoveryCompactor:
    def __init__(self):
        self.check_calls = 0

    def estimate(self, ctx):
        return 0

    async def check_budget(self, ctx):
        self.check_calls += 1
        return None

    async def react_to_overflow(self, ctx, error):
        return ContextDecision(messages=ctx.messages, retry=True, mechanism_id="recover")


class NeverFailTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_next_turn_raising_is_noop(self) -> None:
        provider = FauxProvider()
        tool, _calls = make_tool()
        provider.respond_tool_call("count", {"value": "x"})
        provider.respond_text("done")

        def prepare(ctx):
            raise RuntimeError("prepare boom")

        result = await run_loop(
            make_config(provider, tools=[tool], prepare_next_turn=prepare), "go"
        )
        self.assertFalse(result.is_error)

    async def test_steering_raising_is_noop(self) -> None:
        provider = FauxProvider()
        provider.respond_text("done")

        def steering(ctx):
            raise RuntimeError("steering boom")

        result = await run_loop(make_config(provider, get_steering_messages=steering), "hi")
        self.assertFalse(result.is_error)
        self.assertEqual(1, len(provider.calls[0]["messages"]))

    async def test_follow_up_raising_is_noop(self) -> None:
        provider = FauxProvider()
        provider.respond_text("done")

        def follow_up(ctx):
            raise RuntimeError("follow-up boom")

        result = await run_loop(make_config(provider, get_follow_up_messages=follow_up), "hi")
        self.assertFalse(result.is_error)

    async def test_should_stop_raising_defaults_to_false(self) -> None:
        provider = FauxProvider()
        provider.respond_text("done")

        def should_stop(ctx):
            raise RuntimeError("should-stop boom")

        result = await run_loop(make_config(provider, should_stop_after_turn=should_stop), "hi")
        self.assertFalse(result.is_error)
        self.assertEqual("stop", result.stop_reason)

    async def test_before_tool_raising_proceeds_unblocked(self) -> None:
        provider = FauxProvider()
        tool, calls = make_tool()
        provider.respond_tool_call("count", {"value": "x"})
        provider.respond_text("done")

        def before(ctx):
            raise RuntimeError("before boom")

        result = await run_loop(
            make_config(provider, tools=[tool], before_tool_call=before), "go"
        )
        self.assertFalse(result.is_error)
        self.assertEqual(1, len(calls))  # the tool really executed

    async def test_after_tool_raising_keeps_original_result(self) -> None:
        provider = FauxProvider()
        tool, _calls = make_tool()
        provider.respond_tool_call("count", {"value": "x"})
        provider.respond_text("done")

        def after(ctx, result):
            raise RuntimeError("after boom")

        result = await run_loop(
            make_config(provider, tools=[tool], after_tool_call=after), "go"
        )
        self.assertFalse(result.is_error)
        tool_results = [m for m in result.messages if hasattr(m, "tool_call_id")]
        self.assertTrue(any("count ok" in m.text for m in tool_results))

    async def test_on_partial_raising_does_not_fail_tool(self) -> None:
        provider = FauxProvider()
        tool, calls = make_tool()

        async def execute(ctx):
            await ctx.on_update("partial")
            calls.append(ctx.args)
            return AgentToolResult(content=[TextBlock(text="ok")])

        from dataclasses import replace

        tool = replace(tool, execute=execute)
        provider.respond_tool_call("count", {"value": "x"})
        provider.respond_text("done")

        def broken_display(text):
            raise RuntimeError("display boom")

        result = await run_loop(
            make_config(provider, tools=[tool], on_partial=broken_display), "go"
        )

        self.assertFalse(result.is_error)
        self.assertEqual([{"value": "x"}], calls)

    async def test_invalid_tool_return_becomes_error_result(self) -> None:
        provider = FauxProvider()
        tool, _calls = make_tool()

        from dataclasses import replace

        tool = replace(tool, execute=lambda ctx: None)
        provider.respond_tool_call("count", {"value": "x"})
        provider.respond_text("done")
        result = await run_loop(make_config(provider, tools=[tool]), "go")

        self.assertFalse(result.is_error)
        errors = [m for m in result.messages if getattr(m, "is_error", False)]
        self.assertEqual(1, len(errors))
        self.assertIn("expected AgentToolResult", errors[0].text)

    async def test_provider_sync_raise_is_structured(self) -> None:
        result = await run_loop(make_config(_SyncRaisingProvider()), "hi")
        self.assertTrue(result.is_error)
        self.assertIn("TypeError", result.error_details["error"])

    async def test_provider_midstream_raise_is_structured(self) -> None:
        result = await run_loop(make_config(_MidStreamRaisingProvider()), "hi")
        self.assertTrue(result.is_error)
        self.assertIn("RuntimeError", result.error_details["error"])

    async def test_compactor_check_budget_raising_is_skipped(self) -> None:
        provider = FauxProvider()
        provider.respond_text("done")
        result = await run_agent_loop_with_compactor(
            provider, _CheckBudgetRaisingCompactor(), "hi"
        )
        self.assertFalse(result.is_error)

    async def test_compactor_estimate_raising_enters_ladder(self) -> None:
        provider = FauxProvider()
        provider.respond_fatal(message="bad request", unknown_400=True)
        provider.respond_text("recovered")
        compactor = _EstimateRaisingCompactor()
        result = await run_agent_loop_with_compactor(provider, compactor, "hi")
        self.assertFalse(result.is_error)
        self.assertEqual(1, compactor.react_calls)  # ladder really ran
        self.assertEqual(2, len(provider.calls))  # and the request was retried

    async def test_compactor_react_raising_gives_up_structured(self) -> None:
        provider = FauxProvider()
        provider.respond_overflow()
        result = await run_agent_loop_with_compactor(
            provider, _ReactRaisingCompactor(), "hi"
        )
        self.assertTrue(result.is_error)
        self.assertEqual("context_overflow", result.error_details["kind"])
        self.assertEqual("unavailable", result.error_details["recovery"])

    async def test_core_caps_context_recovery_attempts(self) -> None:
        provider = FauxProvider()
        for _ in range(3):
            provider.respond_overflow()
        config = make_config(provider, max_context_recovery_attempts=2)

        from fruitfly_agent.core.loop import run_agent_loop
        from fruitfly_agent.core.data_model import UserMessage

        result = await run_agent_loop(
            config,
            [UserMessage(content="hi")],
            context_pipeline=_EndlessRecoveryCompactor(),
        )

        self.assertTrue(result.is_error)
        self.assertEqual(3, len(provider.calls))
        self.assertEqual(2, result.error_details["overflow_attempts"])
        self.assertEqual("attempt_limit", result.error_details["recovery"])

    async def test_budget_check_does_not_overwrite_recovery_before_retry(self) -> None:
        provider = FauxProvider()
        provider.respond_overflow()
        provider.respond_text("recovered")
        compactor = _RecordingRecoveryCompactor()

        result = await run_agent_loop_with_compactor(provider, compactor, "hi")

        self.assertFalse(result.is_error, result.error_details)
        self.assertEqual(1, compactor.check_calls)

    async def test_cancelled_error_propagates(self) -> None:
        provider = FauxProvider()
        provider.respond_text("done")
        hooks = HookRegistry()

        def cancel(event):
            raise asyncio.CancelledError()

        hooks.add(BEFORE_RUN, cancel)
        with self.assertRaises(asyncio.CancelledError):
            await run_loop(make_config(provider, hooks=hooks), "hi")


async def run_agent_loop_with_compactor(provider, compactor, prompt):
    from fruitfly_agent.core.loop import run_agent_loop
    from fruitfly_agent.core.data_model import UserMessage

    config = make_config(provider)
    return await run_agent_loop(config, [UserMessage(content=prompt)], context_pipeline=compactor)


if __name__ == "__main__":
    unittest.main()
