"""Lab summarizing compactor, scripted end-to-end (no network)."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.extensions.hooks import BEFORE_COMPACTION, HookRegistry
from fruitfly_agent.core.context import ContextReducer
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.data_model import (
    AssistantMessage,
    TextBlock,
    ToolResultMessage,
    UserMessage,
)
from fruitfly_agent.lab.context_manager.reduction import (
    SummarizingCompactor,
    SummarizingCompactorConfig,
)

from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_tool


class TestSummarizingCompactor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.session = Session(Path(self.tmp.name) / "session.jsonl")
        self.provider = FauxProvider()

    def tearDown(self):
        self.session.close()
        self.tmp.cleanup()

    def build_config(
        self,
        tools,
        context_window: int = 200_000,
        **overrides,
    ):
        kwargs = dict(
            provider=self.provider,
            model="test-model",
            tools=tools,
            max_tokens=100,
            session=self.session,
            context_window=context_window,
        )
        kwargs.update(overrides)
        return AgentLoopConfig(**kwargs)

    # --- L1: budget layer compacts BEFORE the request -------------------------

    def test_implements_core_compactor_protocol(self):
        compactor = SummarizingCompactor(
            SummarizingCompactorConfig(), FauxProvider()
        )
        self.assertIsInstance(compactor, ContextReducer)

    def test_config_validates_serializable_hyperparameters(self):
        for field, value in (
            ("summary_attempts", 0),
            ("summary_max_tokens", 0),
            ("max_shrink_steps", 0),
            ("token_estimator", "missing"),
            ("prompt_version", "missing"),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                SummarizingCompactorConfig(**{field: value})

    async def test_summary_request_uses_exposed_limits_and_model(self):
        summarizer = FauxProvider()
        summarizer.respond_text("summary")
        compactor = SummarizingCompactor(
            SummarizingCompactorConfig(
                reserve_tokens=0, keep_recent_tokens=1,
                summary_word_limit=123,
                summary_max_tokens=456,
                per_message_char_limit=20,
                history_char_limit=80,
            ),
            summarizer,
            summary_model="summary-model",
        )
        from fruitfly_agent.core.data_model import ContextItem, ContextSnapshot

        messages = [
            UserMessage(content="old " + "x" * 100),
            AssistantMessage(content=[TextBlock(text="old answer")]),
            UserMessage(content="recent"),
        ]
        snapshot = ContextSnapshot(
            canonical_items=tuple(
                ContextItem(str(index), message)
                for index, message in enumerate(messages)
            ),
            messages=tuple(messages),
            system_prompt="",
            tools=(),
            context_window=128,
            model="main-model",
            max_tokens=100,
            trigger="budget",
        )

        decision = await compactor.check_budget(snapshot)

        self.assertIsNotNone(decision)
        self.assertEqual("summary-model", summarizer.calls[0]["model"])
        self.assertEqual(456, summarizer.calls[0]["max_tokens"])
        prompt = summarizer.calls[0]["messages"][0].content
        self.assertIn("Under 123 words", prompt)
        self.assertNotIn("x" * 21, prompt)

    async def test_budget_layer_compacts_before_request(self):
        tool, calls = make_tool()
        big = "x" * 4000
        self.provider.respond_text("done")
        summarizer = FauxProvider()
        summarizer.respond_text("old stuff summarized")

        compaction = SummarizingCompactorConfig(
            reserve_tokens=500,
            keep_recent_tokens=300,
        )
        config = self.build_config([tool], context_window=1000)
        compactor = SummarizingCompactor(compaction, summarizer)
        # Two turns of history: old turn (summarized) + recent (kept).
        messages = [
            UserMessage(content=f"old context {big}"),
            AssistantMessage(content=[TextBlock(text="ok")]),
            UserMessage(content="recent work"),
        ]
        result = await run_agent_loop(config, messages, context_pipeline=compactor)
        self.assertFalse(result.is_error, result.error_details)
        # Core persisted the algorithm-neutral proposed projection.
        entries = [e for e in self.session.read_all() if e.type == "compaction"]
        self.assertEqual(len(entries), 1)
        payload = entries[0].payload
        self.assertEqual("summarizing", payload["mechanismId"])
        self.assertEqual("budget", payload["trigger"])
        self.assertGreater(payload["tokensBefore"], 0)
        self.assertEqual(len(payload["messages"]), 2)
        # The projected context starts with the summary custom message.
        self.assertEqual(result.messages[0].role, "custom")

    async def test_budget_layer_skips_when_under_threshold(self):
        self.provider.respond_text("done")
        compaction = SummarizingCompactorConfig(reserve_tokens=100)
        config = self.build_config([])
        compactor = SummarizingCompactor(compaction, self.provider)
        result = await run_agent_loop(config, [UserMessage(content="short")], context_pipeline=compactor)
        self.assertFalse(result.is_error)
        self.assertEqual(
            [e for e in self.session.read_all() if e.type == "compaction"], []
        )

    async def test_before_compaction_hook_can_cancel_core_commit(self):
        self.provider.respond_text("done")
        summarizer = FauxProvider()
        summarizer.respond_text("summary")
        hooks = HookRegistry(session=self.session)

        def cancel(event):
            event.cancel = True

        hooks.add(BEFORE_COMPACTION, cancel)
        compaction = SummarizingCompactorConfig(reserve_tokens=100, keep_recent_tokens=100)
        config = self.build_config([], context_window=1_000, hooks=hooks)
        compactor = SummarizingCompactor(compaction, summarizer)
        messages = [
            UserMessage(content="old " + "x" * 4_000),
            AssistantMessage(content=[TextBlock(text="done")]),
            UserMessage(content="recent"),
        ]

        result = await run_agent_loop(config, messages, context_pipeline=compactor)

        self.assertFalse(result.is_error)
        self.assertEqual([], [e for e in self.session.read_all() if e.type == "compaction"])

    # --- L2: overflow → compact once → retry exactly once ----------------------

    async def test_reactive_layer_compacts_and_retries_once(self):
        tool, calls = make_tool()
        self.provider.respond_overflow("prompt is too long")
        self.provider.respond_text("recovered")
        summarizer = FauxProvider()
        summarizer.respond_text("old stuff summarized")

        compaction = SummarizingCompactorConfig(
            reserve_tokens=300,
            reactive_keep_recent_tokens=200,
        )
        config = self.build_config([tool], context_window=1000)
        compactor = SummarizingCompactor(compaction, summarizer)
        messages = [
            UserMessage(content="old " + "x" * 800),
            AssistantMessage(content=[TextBlock(text="ok")]),
            UserMessage(content="recent"),
        ]
        result = await run_agent_loop(config, messages, context_pipeline=compactor)
        self.assertFalse(result.is_error, result.error_details)
        self.assertEqual(len(self.provider.calls), 2)  # fail once, retry once
        self.assertEqual(
            len([e for e in self.session.read_all() if e.type == "compaction"]), 1
        )

    async def test_without_compactor_overflow_returns_structured(self):
        self.provider.respond_overflow("prompt is too long")
        config = self.build_config([])
        result = await run_agent_loop(config, [UserMessage(content="hi")], context_pipeline=None)
        self.assertTrue(result.is_error)
        self.assertEqual(result.error_details["kind"], "context_overflow")

    # --- L3: persistent overflow → give up structured, never raise -------------

    async def test_last_resort_gives_up_structured(self):
        # A context that CANNOT be shrunk: one huge user turn, no safe cut.
        # The ladder must give up structured, never raise.
        self.provider.respond_overflow("prompt is too long")
        self.provider.respond_overflow("prompt is too long")
        summarizer = FauxProvider()
        summarizer.respond_text("summary")
        compaction = SummarizingCompactorConfig(
            reserve_tokens=50,
            reactive_keep_recent_tokens=100,
        )
        config = self.build_config([], context_window=300)
        compactor = SummarizingCompactor(compaction, summarizer)
        messages = [UserMessage(content="a" * 400)]
        result = await run_agent_loop(config, messages, context_pipeline=compactor)
        self.assertTrue(result.is_error)
        self.assertEqual(result.error_details["kind"], "context_overflow")
        self.assertIsInstance(result.messages, list)

    async def test_summarization_failure_preserves_history_and_ends_overflow(self):
        # Summary failure must not replace history or retry a broken projection.
        self.provider.respond_overflow("prompt is too long")
        self.provider.respond_text("recovered after placeholder compaction")

        class FailingSummarizer:
            def __init__(self):
                self.calls = 0

            def __call__(self, ctx, *, signal=None):
                self.calls += 1

                async def gen():
                    raise ValueError("summarizer down")
                    yield  # pragma: no cover

                from fruitfly_agent.core.model_stream import AssistantMessageEventStream

                return AssistantMessageEventStream(gen())

        summarizer = FailingSummarizer()
        compaction = SummarizingCompactorConfig(reserve_tokens=100)
        config = self.build_config([], context_window=800)
        compactor = SummarizingCompactor(compaction, summarizer)
        result = await run_agent_loop(
            config,
            [
                UserMessage(content="old " + "c" * 600),
                AssistantMessage(content=[TextBlock(text="ok")]),
                UserMessage(content="recent"),
            ],
            context_pipeline=compactor,
        )
        self.assertTrue(result.is_error)
        self.assertEqual("context_overflow", result.error_details["kind"])
        self.assertEqual(1, len(self.provider.calls))
        self.assertEqual("old " + "c" * 600, result.messages[0].content)
        self.assertGreater(summarizer.calls, 0)
        self.assertEqual([], [e for e in self.session.read_all() if e.type == "compaction"])


if __name__ == "__main__":
    unittest.main()
