"""Renderer-neutral multi-turn interaction and event behavior."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import (
    AgentLoopResult,
    AgentToolResult,
    AssistantMessage,
    ContextDecision,
    TextBlock,
)
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone, TextDelta
from fruitfly_agent.core.extensions.hooks import (
    BEFORE_COMPACTION,
    BeforeCompactionEvent,
    HookRegistry,
)
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.interactive import (
    AssistantTextDelta,
    CompactionStarted,
    InteractiveSession,
    RunActivityChanged,
    RunFinished,
    RunStarted,
    ToolFinished,
    ToolOutput,
    ToolStarted,
)
from tests.support.faux_provider import FauxProvider


class _ObservedCompactor:
    def __init__(self, hooks: HookRegistry) -> None:
        self.hooks = hooks

    def estimate(self, ctx) -> int:
        return 10

    async def check_budget(self, ctx):
        return ContextDecision(
            messages=ctx.messages,
            mechanism_id="observed-test",
            estimated_tokens_before=10,
        )

    async def react_to_overflow(self, ctx, error):
        return None


class InteractiveSessionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "session.jsonl"

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_multiple_prompts_share_context_and_persist_user_messages(self) -> None:
        provider = FauxProvider()
        provider.respond_text("first")
        provider.respond_text("second")
        events = []
        with Session(self.path) as durable:
            config = AgentLoopConfig(
                provider=provider,
                model="offline-model",
                session=durable,
                hooks=HookRegistry(session=durable),
            )
            app = InteractiveSession(config, event_sink=events.append)
            await app.submit("one")
            await app.submit("two")

            self.assertEqual(
                [message.role for message in provider.calls[1]["messages"]],
                ["user", "assistant", "user"],
            )
            self.assertEqual(
                [message.role for message in durable.messages()],
                ["user", "assistant", "user", "assistant"],
            )

        starts = [event for event in events if isinstance(event, RunStarted)]
        finishes = [event for event in events if isinstance(event, RunFinished)]
        deltas = [event for event in events if isinstance(event, AssistantTextDelta)]
        self.assertEqual([event.text for event in deltas], ["first", "second"])
        self.assertEqual(len(starts), 2)
        self.assertEqual(len(finishes), 2)
        self.assertNotEqual(starts[0].run_id, starts[1].run_id)
        self.assertEqual(starts[0].sequence, 1)
        self.assertEqual(starts[1].sequence, 1)
        json.dumps([event.to_dict() for event in events])

        waiting = [
            event
            for event in events
            if isinstance(event, RunActivityChanged)
            and event.phase == "waiting_model"
        ]
        self.assertEqual([event.request_index for event in waiting], [1, 1])

    async def test_activity_events_follow_model_and_tool_lifecycle(self) -> None:
        provider = FauxProvider()
        provider.respond_tool_call("echo", {"value": "hi"})
        provider.respond_text("done")
        events = []

        async def execute(ctx):
            return AgentToolResult(content=[TextBlock("tool result")])

        tool = AgentTool(
            name="echo",
            label="echo",
            description="offline echo",
            parameters={"type": "object", "properties": {}},
            execute=execute,
        )
        app = InteractiveSession(
            AgentLoopConfig(
                provider=provider,
                model="offline-model",
                tools=(tool,),
            ),
            event_sink=events.append,
        )

        await app.submit("use echo")

        activities = [
            event for event in events if isinstance(event, RunActivityChanged)
        ]
        self.assertEqual(
            [event.phase for event in activities],
            [
                "waiting_model",
                "running_tool",
                "processing_tool_result",
                "waiting_model",
                "receiving_answer",
                "finalizing",
            ],
        )
        self.assertEqual(
            [
                event.request_index
                for event in activities
                if event.phase == "waiting_model"
            ],
            [1, 2],
        )
        self.assertEqual(activities[1].activity_id, "call_1")
        self.assertEqual(activities[1].subject, "echo")
        json.dumps([event.to_dict() for event in activities])

    async def test_tool_and_compaction_hooks_become_frontend_events(self) -> None:
        provider = FauxProvider()
        provider.respond_tool_call("echo", {"value": "hi"})
        provider.respond_text("done")
        events = []
        partials = []
        hooks = HookRegistry()

        async def execute(ctx):
            if ctx.on_update is not None:
                await ctx.on_update("working\n")
            return AgentToolResult(content=[TextBlock("tool result")])

        tool = AgentTool(
            name="echo",
            label="echo",
            description="offline echo",
            parameters={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
            execute=execute,
        )
        config = AgentLoopConfig(
            provider=provider,
            model="offline-model",
            tools=[tool],
            hooks=hooks,
            on_partial=partials.append,
        )
        app = InteractiveSession(
            config,
            context_pipeline=_ObservedCompactor(hooks),
            tool_categories={"echo": "memory"},
            event_sink=events.append,
        )

        result = await app.submit("use echo")

        self.assertFalse(result.is_error)
        self.assertTrue(any(isinstance(event, ToolStarted) for event in events))
        self.assertTrue(any(isinstance(event, ToolOutput) for event in events))
        self.assertTrue(any(isinstance(event, ToolFinished) for event in events))
        self.assertEqual(
            {
                event.category
                for event in events
                if isinstance(event, (ToolStarted, ToolFinished))
            },
            {"memory"},
        )
        self.assertEqual(partials, ["working\n"])
        self.assertEqual(
            len([event for event in events if isinstance(event, CompactionStarted)]),
            2,
        )

    async def test_observation_does_not_mutate_shared_hook_owners(self) -> None:
        provider = FauxProvider()
        provider.respond_tool_call("echo", {"value": "hi"})
        provider.respond_text("done")
        hooks = HookRegistry()
        before = {
            name: len(handlers)
            for name, handlers in hooks._handlers.items()
        }

        async def execute(ctx):
            return AgentToolResult(content=[TextBlock("tool result")])

        tool = AgentTool(
            name="echo",
            label="echo",
            description="offline echo",
            parameters={"type": "object", "properties": {}},
            execute=execute,
        )
        config = AgentLoopConfig(
            provider=provider,
            model="offline-model",
            tools=[tool],
            hooks=hooks,
        )
        compactor = _ObservedCompactor(hooks)
        events = []

        app = InteractiveSession(
            config,
            context_pipeline=compactor,
            event_sink=events.append,
        )
        result = await app.submit("use echo")

        self.assertFalse(result.is_error)
        self.assertEqual(
            {name: len(handlers) for name, handlers in hooks._handlers.items()},
            before,
        )
        self.assertIs(config.hooks, hooks)
        self.assertIs(compactor.hooks, hooks)
        self.assertTrue(any(isinstance(event, ToolStarted) for event in events))
        self.assertTrue(any(isinstance(event, CompactionStarted) for event in events))

    async def test_renderer_failure_does_not_change_run(self) -> None:
        provider = FauxProvider()
        provider.respond_text("still works")

        def broken_sink(event):
            raise RuntimeError("renderer broke")

        app = InteractiveSession(
            AgentLoopConfig(provider=provider, model="offline-model"),
            event_sink=broken_sink,
        )
        result = await app.submit("hello")
        self.assertFalse(result.is_error)
        self.assertEqual(result.messages[-1].text, "still works")

    async def test_cancel_sets_the_core_signal_for_the_active_run(self) -> None:
        started = asyncio.Event()

        async def wait_for_cancel(config, messages, *, signal, context_pipeline):
            started.set()
            await signal.wait()
            return AgentLoopResult(
                messages=list(messages),
                stop_reason="aborted",
                model=config.model,
            )

        app = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="offline-model"),
            run_loop=wait_for_cancel,
        )
        task = asyncio.create_task(app.submit("long task"))
        await started.wait()

        self.assertTrue(app.running)
        self.assertTrue(app.cancel())
        result = await task

        self.assertEqual(result.stop_reason, "aborted")
        self.assertFalse(app.running)
        self.assertFalse(app.cancel())

    async def test_steering_is_injected_before_the_next_provider_request(self) -> None:
        provider = FauxProvider()
        provider.respond_tool_call("pause", {})
        provider.respond_text("adjusted")
        entered_tool = asyncio.Event()
        release_tool = asyncio.Event()

        async def execute(ctx):
            entered_tool.set()
            await release_tool.wait()
            return AgentToolResult(content=[TextBlock("done")])

        tool = AgentTool(
            name="pause",
            label="pause",
            description="wait for steering",
            parameters={"type": "object", "properties": {}},
            execute=execute,
        )
        app = InteractiveSession(
            AgentLoopConfig(
                provider=provider,
                model="offline-model",
                tools=(tool,),
            )
        )
        task = asyncio.create_task(app.submit("start"))
        await entered_tool.wait()

        self.assertTrue(app.steer("use the safer path"))
        release_tool.set()
        result = await task

        self.assertFalse(result.is_error)
        self.assertEqual(
            [message.role for message in provider.calls[1]["messages"]],
            ["user", "assistant", "toolResult", "user"],
        )
        self.assertEqual(
            provider.calls[1]["messages"][-1].content,
            "use the safer path",
        )

    async def test_input_during_final_response_gets_follow_up_request_and_is_persisted(self) -> None:
        provider = FauxProvider()
        entered_response = asyncio.Event()
        finish_response = asyncio.Event()
        previous_follow_up_calls = 0

        async def stream_final():
            yield TextDelta(text="first answer")
            entered_response.set()
            await finish_response.wait()
            yield StreamDone(result=AssistantMessage(content=[TextBlock("first answer")]))

        provider.script.append(
            lambda ctx, signal=None: AssistantMessageEventStream(stream_final())
        )
        provider.respond_text("revised answer")

        def previous_follow_up(ctx):
            nonlocal previous_follow_up_calls
            previous_follow_up_calls += 1
            return []

        with Session(self.path) as durable:
            app = InteractiveSession(
                AgentLoopConfig(
                    provider=provider, model="offline-model", session=durable,
                    get_follow_up_messages=previous_follow_up,
                )
            )
            task = asyncio.create_task(app.submit("initial request"))
            await entered_response.wait()
            self.assertTrue(app.steer("change the conclusion"))
            finish_response.set()
            result = await task
            self.assertFalse(result.is_error)
            self.assertEqual(len(provider.calls), 2)
            self.assertEqual(provider.calls[1]["messages"][-1].content, "change the conclusion")
            self.assertEqual(
                [message.content for message in durable.messages() if message.role == "user"],
                ["initial request", "change the conclusion"],
            )
            self.assertEqual(previous_follow_up_calls, 2)

    async def test_input_after_final_follow_up_poll_is_not_accepted_as_current_run(self) -> None:
        provider = FauxProvider()
        provider.respond_text("done")
        entered_stop = asyncio.Event()
        finish_stop = asyncio.Event()

        async def should_stop(ctx):
            entered_stop.set()
            await finish_stop.wait()
            return True

        app = InteractiveSession(
            AgentLoopConfig(
                provider=provider, model="offline-model",
                should_stop_after_turn=should_stop,
            )
        )
        task = asyncio.create_task(app.submit("initial request"))
        await entered_stop.wait()
        self.assertFalse(app.steer("new request"))
        finish_stop.set()
        await task


if __name__ == "__main__":
    unittest.main()
