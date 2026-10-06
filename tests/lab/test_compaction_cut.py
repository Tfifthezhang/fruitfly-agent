"""find_cut_point invariants: boundaries, pairing, the #1555 no-op fix."""

import unittest

from fruitfly_agent.lab.context_manager.reduction.cut import find_cut_point
from fruitfly_agent.core.data_model import (
    AssistantMessage,
    CustomMessage,
    TextBlock,
    ToolCallBlock,
    ToolResultMessage,
    UserMessage,
)


def est(message) -> int:
    if isinstance(message, (UserMessage, CustomMessage)):
        text = message.content if isinstance(message, UserMessage) and isinstance(message.content, str) else message.text
        return len(text)
    if isinstance(message, AssistantMessage):
        return 10
    if isinstance(message, ToolResultMessage):
        return len(message.text)
    return 0


def user(text):
    return UserMessage(content=text)


def turn(i: int) -> list:
    """A complete turn: user, assistant(tool call), tool result, assistant(text)."""
    return [
        user(f"turn {i}"),
        AssistantMessage(content=[ToolCallBlock(id=f"c{i}", name="bash", input={})]),
        ToolResultMessage(tool_call_id=f"c{i}", content=[TextBlock(text="x" * 20)]),
        AssistantMessage(content=[TextBlock(text="done")]),
    ]


class TestFindCutPoint(unittest.TestCase):
    def test_empty_returns_none(self):
        self.assertIsNone(find_cut_point([], 100, est))

    def test_under_threshold_returns_none(self):
        messages = turn(1)
        self.assertIsNone(find_cut_point(messages, 10_000, est))

    def test_cut_lands_on_user_boundary(self):
        messages = turn(1) + turn(2) + turn(3)
        cut = find_cut_point(messages, 60, est)
        self.assertIsNotNone(cut)
        self.assertIsInstance(messages[cut], UserMessage)
        # Tool results never cut: the retained tail must start with a complete
        # user turn (the most recent one that fits the keep-recent budget).
        self.assertEqual(messages[cut].content, "turn 3")

    def test_tool_results_never_cut(self):
        # A boundary inside a turn would orphan the tool result.
        messages = turn(1) + turn(2)
        cut = find_cut_point(messages, 30, est)
        self.assertIsNotNone(cut)
        self.assertIsInstance(messages[cut], UserMessage)

    def test_single_huge_turn_never_noop(self):
        # One turn bigger than keep_recent: cut at its start — the WHOLE turn
        # is kept, never a no-op fallback to the oldest boundary.
        messages = turn(1) + [
            user("big"),
            AssistantMessage(content=[ToolCallBlock(id="c", name="bash", input={})]),
            ToolResultMessage(tool_call_id="c", content=[TextBlock(text="y" * 500)]),
        ]
        cut = find_cut_point(messages, 100, est)
        self.assertIsNotNone(cut)
        self.assertEqual(cut, 4)  # start of the big turn
        self.assertEqual(messages[cut].content, "big")

    def test_cut_never_zero(self):
        # Single user message + huge tail: no boundary inside; the boundary is
        # index 0 → None (callers treat None as no-op; L2/L3 absorb).
        messages = [
            user("only turn"),
            ToolResultMessage(tool_call_id="c", content=[TextBlock(text="z" * 500)]),
        ]
        cut = find_cut_point(messages, 100, est)
        self.assertIsNone(cut)

    def test_compaction_summary_is_boundary(self):
        messages = [
            CustomMessage(kind="compactionSummary", text="old summary"),
            user("recent"),
            AssistantMessage(content=[ToolCallBlock(id="c", name="bash", input={})]),
            ToolResultMessage(tool_call_id="c", content=[TextBlock(text="w" * 300)]),
        ]
        cut = find_cut_point(messages, 150, est)
        self.assertIsNotNone(cut)
        self.assertIsInstance(messages[cut], UserMessage)


if __name__ == "__main__":
    unittest.main()
