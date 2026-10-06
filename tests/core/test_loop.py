"""Loop invariants — G1..G5 gates (faux provider, zero network)."""

import asyncio
import unittest

from fruitfly_agent.core.config import BeforeToolCallResult, PrepareNextTurnResult
from fruitfly_agent.core.data_model import (
    AssistantMessage,
    TextBlock,
    ToolCallBlock,
    ToolResultMessage,
    Usage,
    UserMessage,
)
from fruitfly_agent.core.extensions.hooks import (
    BEFORE_REQUEST,
    BEFORE_TOOL,
    HookRegistry,
    ToolEvent,
)
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.model_stream import StreamDone, StreamError, TextDelta

from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_config, make_tool, run_loop


class TestLoop(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = FauxProvider()

    async def test_simple_text_turn(self):
        self.provider.respond_text("hello there")
        config = make_config(self.provider)
        result = await run_loop(config, "say hi")
        self.assertFalse(result.is_error, result.error_details)
        self.assertEqual(result.stop_reason, "stop")
        self.assertEqual(result.messages[-1].text, "hello there")
        self.assertEqual(len(self.provider.calls), 1)

    # --- G1: length-truncated tool calls are NEVER executed -----------------

    async def test_length_truncated_tool_calls_not_executed(self):
        tool, calls = make_tool()
        self.provider.respond_length_with_tool_call("count", {"value": "x"})
        self.provider.respond_text("retried and done")
        config = make_config(self.provider, [tool])
        result = await run_loop(config, "do it")
        self.assertFalse(result.is_error)
        self.assertEqual(calls, [])  # the tool was never executed
        # An error tool result told the model its call was truncated.
        errors = [
            m
            for m in result.messages
            if isinstance(m, ToolResultMessage) and m.is_error
        ]
        self.assertEqual(len(errors), 1)
        self.assertIn("NOT executed", errors[0].text)

    # --- G2: terminate semantics -------------------------------------------

    async def test_partial_terminate_continues(self):
        tool, calls = make_tool()
        terminator, calls2 = make_tool("terminator", terminate=True)
        self.provider.respond_tool_call("count", {"value": "a"})
        self.provider.respond_tool_call("count", {"value": "b"})
        self.provider.respond_tool_call("terminator", {"value": "c"})
        config = make_config(self.provider, [tool, terminator])
        result = await run_loop(config, "work")
        self.assertFalse(result.is_error)
        # First batches had count only (no terminate) → loop continued.
        # Terminator batch: every result terminate=True → run ended.
        self.assertEqual(result.stop_reason, "stop")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(calls2), 1)

    async def test_all_terminate_stops(self):
        tool, calls = make_tool("terminator", terminate=True)
        self.provider.respond_tool_call("terminator", {"value": "x"})
        self.provider.respond_text("should never be requested")
        config = make_config(self.provider, [tool])
        result = await run_loop(config, "stop now")
        self.assertFalse(result.is_error)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.provider.calls), 1)  # second response never consumed

    # --- G3: nothing can kill the loop --------------------------------------

    async def test_unknown_tool_error_result(self):
        self.provider.respond_tool_call("ghost", {"value": "x"})
        self.provider.respond_text("done")
        config = make_config(self.provider, [])
        result = await run_loop(config, "call ghost")
        self.assertFalse(result.is_error)
        errors = [
            m for m in result.messages if isinstance(m, ToolResultMessage) and m.is_error
        ]
        self.assertEqual(len(errors), 1)
        self.assertIn("not found", errors[0].text)

    async def test_schema_failure_error_result(self):
        tool, calls = make_tool()
        self.provider.respond_tool_call("count", {"value": 42})  # coerced ok
        self.provider.respond_tool_call("count", {"bogus": 1})  # missing required
        self.provider.respond_text("done")
        config = make_config(self.provider, [tool])
        result = await run_loop(config, "call count")
        self.assertFalse(result.is_error)
        errors = [
            m for m in result.messages if isinstance(m, ToolResultMessage) and m.is_error
        ]
        self.assertEqual(len(errors), 1)
        self.assertIn("missing required argument", errors[0].text)
        self.assertEqual(len(calls), 1)

    async def test_tool_exception_error_result(self):
        async def boom(ctx):
            raise RuntimeError("kaboom")

        tool = make_tool("count")[0]
        from dataclasses import replace

        tool = replace(tool, execute=boom)
        self.provider.respond_tool_call("count", {"value": "x"})
        self.provider.respond_text("recovered")
        config = make_config(self.provider, [tool])
        result = await run_loop(config, "do it")
        self.assertFalse(result.is_error)
        errors = [
            m for m in result.messages if isinstance(m, ToolResultMessage) and m.is_error
        ]
        self.assertEqual(len(errors), 1)
        self.assertIn("kaboom", errors[0].text)

    async def test_blocked_tool_becomes_error_result(self):
        tool, calls = make_tool()
        self.provider.respond_tool_call("count", {"value": "x"})
        self.provider.respond_text("ok")

        def block(ctx):
            return BeforeToolCallResult(block=True, reason="not allowed")

        config = make_config(self.provider, [tool], before_tool_call=block)
        result = await run_loop(config, "do it")
        self.assertFalse(result.is_error)
        self.assertEqual(calls, [])  # never executed
        errors = [
            m for m in result.messages if isinstance(m, ToolResultMessage) and m.is_error
        ]
        self.assertEqual(len(errors), 1)
        self.assertIn("not allowed", errors[0].text)

    async def test_hook_exception_run_survives(self):
        tool, calls = make_tool()
        self.provider.respond_tool_call("count", {"value": "x"})
        self.provider.respond_text("done")

        def bad_hook(event: ToolEvent) -> None:
            raise RuntimeError("hook blew up")

        hooks = HookRegistry()
        hooks.add(BEFORE_TOOL, bad_hook)
        config = make_config(self.provider, [tool], hooks=hooks)
        result = await run_loop(config, "do it")
        self.assertFalse(result.is_error)
        self.assertEqual(len(calls), 1)  # tool still executed after hook failure

    async def test_before_tool_hook_rewrites_args_and_exposes_call_id(self):
        tool, calls = make_tool()
        self.provider.respond_tool_call("count", {"value": "original"})
        self.provider.respond_text("done")
        hooks = HookRegistry()
        observed_ids: list[str] = []

        def rewrite(event):
            event.args["value"] = "rewritten"

        def observe(event):
            observed_ids.append(event.tool_call_id)

        hooks.add(BEFORE_TOOL, rewrite)
        hooks.on(BEFORE_TOOL, observe)
        result = await run_loop(make_config(self.provider, [tool], hooks=hooks), "go")

        self.assertFalse(result.is_error)
        self.assertEqual([{"value": "rewritten"}], calls)
        self.assertEqual(["call_1"], observed_ids)

    async def test_before_request_commits_before_budget_check(self):
        self.provider.respond_text("done")
        hooks = HookRegistry()

        def prepare(event):
            event.system_prompt = "expanded prompt"
            event.model = "hook-model"
            event.max_tokens = 123

        class RecordingCompactor:
            def __init__(self):
                self.seen = None

            def estimate(self, ctx):
                return 0

            async def check_budget(self, ctx):
                self.seen = (ctx.system_prompt, ctx.model, ctx.max_tokens)
                return None

            async def react_to_overflow(self, ctx, error):
                return None

        hooks.add(BEFORE_REQUEST, prepare)
        compactor = RecordingCompactor()
        config = make_config(self.provider, hooks=hooks)

        result = await run_agent_loop(
            config, [UserMessage(content="go")], context_pipeline=compactor
        )

        self.assertFalse(result.is_error)
        self.assertEqual(("expanded prompt", "hook-model", 123), compactor.seen)
        self.assertEqual("hook-model", self.provider.calls[0]["model"])
        self.assertEqual(123, self.provider.calls[0]["max_tokens"])
        self.assertEqual("hook-model", result.model)

    # --- G4: prepareNextTurn / steering / abort ------------------------------

    async def test_prepare_next_turn_swaps_model(self):
        tool, calls = make_tool()
        self.provider.respond_tool_call("count", {"value": "a"})
        self.provider.respond_text("second")

        def swap(ctx):
            return PrepareNextTurnResult(model="swapped-model")

        config = make_config(self.provider, [tool], prepare_next_turn=swap)
        result = await run_loop(config, "two turns")
        self.assertFalse(result.is_error)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.provider.calls[1]["model"], "swapped-model")

    async def test_steering_injected_between_turns(self):
        tool, calls = make_tool()
        self.provider.respond_tool_call("count", {"value": "a"})
        self.provider.respond_text("done")
        steering: list = []

        def get_steering(ctx):
            drained = list(steering)
            steering.clear()
            return drained

        def add_steering(ctx):
            # Deterministic injection point: prepare_next_turn runs between turns,
            # right before the steering poll of the next iteration.
            steering.append(UserMessage(content="mid-run instruction"))
            return None

        config = make_config(
            self.provider,
            [tool],
            get_steering_messages=get_steering,
            prepare_next_turn=add_steering,
        )
        result = await run_loop(config, "work")
        self.assertFalse(result.is_error)
        self.assertEqual(len(calls), 1)
        # The steering message reached the model: the second call's messages include it.
        second = self.provider.calls[1]
        self.assertTrue(
            any(
                isinstance(m, UserMessage) and m.content == "mid-run instruction"
                for m in second["messages"]
            )
        )

    async def test_abort_returns_aborted(self):
        tool, calls = make_tool()
        self.provider.respond_tool_call("count", {"value": "a"})
        self.provider.respond_text("should never be requested")
        signal = asyncio.Event()

        def abort_between_turns(ctx):
            # Deterministic: runs after the first tool batch, before request 2.
            signal.set()
            return None

        config = make_config(self.provider, [tool], prepare_next_turn=abort_between_turns)
        result = await run_loop(config, "work", signal=signal)
        self.assertEqual(result.stop_reason, "aborted")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.provider.calls), 1)  # second request never sent

    # --- G5: garbage streams never raise -------------------------------------

    async def test_garbage_stream_structured_return(self):
        def garbage(ctx, *, signal=None):
            async def broken_gen():
                yield TextDelta(text="partial")
                raise ValueError("stream imploded")

            from fruitfly_agent.core.model_stream import AssistantMessageEventStream

            return AssistantMessageEventStream(broken_gen())

        from dataclasses import replace

        config = replace(make_config(self.provider), provider=garbage)
        result = await run_loop(config, "anything")
        self.assertTrue(result.is_error)
        self.assertIn("stream imploded", result.error_details["error"])

    async def test_script_exhausted_structured_return(self):
        config = make_config(self.provider, [])
        result = await run_loop(config, "anything")  # no scripted responses
        self.assertTrue(result.is_error)
        self.assertIn("script exhausted", result.error_details["error"])


if __name__ == "__main__":
    unittest.main()
