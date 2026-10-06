"""Single summarizer safety, composition and bounded recovery, offline."""
from dataclasses import replace
import unittest

from fruitfly_agent.core.data_model import (
    AssistantMessage, ContextItem, ContextSnapshot, CustomMessage, ImageBlock,
    TextBlock, ToolCallBlock, ToolResultMessage, UserMessage,
)
from fruitfly_agent.lab.context_manager.reduction import SummarizingCompactor, SummarizingCompactorConfig
from fruitfly_agent.lab.context_manager.reduction.cut import find_cut_point, valid_tool_links
from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_tool


def snapshot(messages=None, **overrides):
    messages = tuple(messages or (
        UserMessage(content="old task " + "x" * 2000),
        AssistantMessage(content=[TextBlock("completed step")]),
        UserMessage(content="latest task"),
    ))
    values = dict(messages=messages, canonical_items=tuple(ContextItem(str(i), m) for i, m in enumerate(messages)),
                  system_prompt="", tools=(), context_window=256, model="main", max_tokens=32, trigger="budget")
    values.update(overrides)
    return ContextSnapshot(**values)


def compactor(provider, **overrides):
    values = dict(reserve_tokens=0, keep_recent_tokens=1, reactive_keep_recent_tokens=1, summary_attempts=1)
    values.update(overrides)
    return SummarizingCompactor(SummarizingCompactorConfig(**values), provider)


class ReductionSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_blank_truncated_error_and_tool_outputs(self):
        responses = (
            AssistantMessage([TextBlock("   \n")], stop_reason="stop"),
            AssistantMessage([TextBlock("summary")], stop_reason="length"),
            AssistantMessage([TextBlock("summary")], stop_reason="error"),
            AssistantMessage([TextBlock("summary"), ToolCallBlock("c", "write", {})], stop_reason="stop"),
        )
        original = snapshot()
        before = [m.to_dict() for m in original.messages]
        for response in responses:
            provider = FauxProvider()
            provider.respond(response)
            self.assertIsNone(await compactor(provider).check_budget(original))
            self.assertEqual(before, [m.to_dict() for m in original.messages])

    async def test_rejects_larger_and_smaller_but_still_over_budget(self):
        for text in ("s" * 3000, "s" * 1000):
            provider = FauxProvider()
            provider.respond_text(text)
            self.assertIsNone(await compactor(provider).check_budget(snapshot()))

    async def test_accepts_only_fitting_smaller_projection_and_keeps_tail(self):
        provider = FauxProvider()
        provider.respond_text("old task and pending work")
        reducer = compactor(provider)
        original = snapshot()
        decision = await reducer.check_budget(original)
        self.assertIsNotNone(decision)
        self.assertEqual(original.messages[-1], decision.messages[-1])
        self.assertLess(reducer.estimate(replace(original, messages=decision.messages)), reducer.estimate(original))
        self.assertLessEqual(reducer.estimate(replace(original, messages=decision.messages)), original.context_window - original.max_tokens)
        self.assertFalse(decision.retry)

    async def test_fixed_prompt_tools_and_output_cannot_be_discarded(self):
        tool, _ = make_tool()
        for changes in ({"system_prompt": "s" * 2000}, {"tools": (replace(tool, description="t" * 2000),)}, {"max_tokens": 256}):
            provider = FauxProvider()
            self.assertIsNone(await compactor(provider).check_budget(snapshot(**changes)))
            self.assertEqual([], provider.calls)

    async def test_indivisible_latest_turn_remains_without_auxiliary_call(self):
        provider = FauxProvider()
        messages = [UserMessage("old"), AssistantMessage([TextBlock("old")]), UserMessage("x" * 2000)]
        self.assertIsNone(await compactor(provider).react_to_overflow(snapshot(messages, trigger="overflow", overflow_attempt=1), RuntimeError()))
        self.assertEqual([], provider.calls)

    async def test_no_permanent_suppression_after_invalid_summary(self):
        provider = FauxProvider()
        reducer = compactor(provider)
        provider.respond_text(" ")
        self.assertIsNone(await reducer.check_budget(snapshot()))
        provider.respond_text("summary")
        self.assertIsNotNone(await reducer.check_budget(snapshot()))

    async def test_overflow_requires_progress_and_obeys_attempt_limit(self):
        provider = FauxProvider()
        provider.respond_text("summary")
        provider.respond_text("summary")
        reducer = compactor(provider)
        original = snapshot(trigger="overflow", overflow_attempt=1)
        first = await reducer.react_to_overflow(original, RuntimeError())
        self.assertTrue(first.retry)
        next_snapshot = replace(original, messages=first.messages, overflow_attempt=2)
        self.assertIsNone(await reducer.react_to_overflow(next_snapshot, RuntimeError()))
        self.assertIsNone(await reducer.react_to_overflow(replace(original, overflow_attempt=100), RuntimeError()))
        self.assertEqual(2, len(provider.calls))

    async def test_serializes_text_blocks_calls_results_errors_and_previous_summary(self):
        provider = FauxProvider()
        provider.respond_text("summary")
        messages = [
            CustomMessage("compactionSummary", "prior decisions"),
            UserMessage([TextBlock("important constraint"), ImageBlock("base64-secret", "image/png")]),
            AssistantMessage([ToolCallBlock("call", "write", {"path": "important.txt", "content": "value"})]),
            ToolResultMessage("call", [TextBlock("failed " + "x" * 2000)], is_error=True),
            UserMessage("latest task"),
        ]
        decision = await compactor(provider).check_budget(snapshot(messages))
        self.assertIsNotNone(decision)
        prompt = provider.calls[0]["messages"][0].content
        for text in ("prior decisions", "important constraint", "image/png", "write", "important.txt", "error=True", "content omitted"):
            self.assertIn(text, prompt)
        self.assertNotIn("base64-secret", prompt)

    async def test_retains_projected_tail_and_external_reference_deterministically(self):
        reference = "context://sha256/" + "a" * 64
        messages = [UserMessage("reference: " + reference + "\n" + "x" * 2000), AssistantMessage([TextBlock("old")]), UserMessage("projected tail")]
        canonical = tuple(ContextItem(str(i), UserMessage("canonical " + "y" * 1000)) for i in range(3))
        provider = FauxProvider()
        provider.respond_text("summary without references")
        decision = await compactor(provider).check_budget(snapshot(messages, canonical_items=canonical))
        self.assertIsNotNone(decision)
        self.assertIn(reference, decision.messages[0].text)
        self.assertEqual(messages[-1], decision.messages[-1])
        self.assertNotIn("canonical", decision.messages[0].text)

    async def test_auxiliary_input_and_output_have_separate_model_budget(self):
        provider = FauxProvider()
        provider.respond_text("summary")
        reducer = SummarizingCompactor(SummarizingCompactorConfig(reserve_tokens=0, keep_recent_tokens=1), provider,
                                      summary_context_window=256, summary_output_limit=32)
        self.assertIsNotNone(await reducer.check_budget(snapshot()))
        call = provider.calls[0]
        self.assertEqual(32, call["max_tokens"])
        self.assertLessEqual(reducer.estimate_tokens(call["system_prompt"] + call["messages"][0].content) + 16 + 32, 256)
        self.assertIn("content omitted", call["messages"][0].content)

    async def test_invalid_or_pending_tool_links_are_not_compressed(self):
        for messages in (
            [UserMessage("old" * 1000), ToolResultMessage("missing", [TextBlock("result")]), UserMessage("latest")],
            [UserMessage("old" * 1000), AssistantMessage([ToolCallBlock("c", "read", {})]), UserMessage("latest")],
        ):
            provider = FauxProvider()
            self.assertIsNone(await compactor(provider).check_budget(snapshot(messages)))
            self.assertEqual([], provider.calls)

    def test_steering_boundary_cannot_split_a_tool_pair(self):
        messages = [UserMessage("old"), AssistantMessage([TextBlock("answer")]), UserMessage("task"),
                    AssistantMessage([ToolCallBlock("c", "read", {})]), UserMessage("steering"),
                    ToolResultMessage("c", [TextBlock("result")])]
        cut = find_cut_point(messages, 1, lambda _: 1)
        self.assertEqual(2, cut)
        self.assertTrue(valid_tool_links(messages[cut:]))
