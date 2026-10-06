"""Anthropic codec invariants: merging, pairing normalization, user-first."""

import unittest

from fruitfly_agent.providers.anthropic_codec import convert_to_anthropic
from fruitfly_agent.core.data_model import (
    AssistantMessage,
    CustomMessage,
    TextBlock,
    ToolCallBlock,
    ToolResultMessage,
    UserMessage,
)


class TestConversion(unittest.TestCase):
    def test_consecutive_tool_results_merge_into_one_user_message(self):
        messages = [
            UserMessage(content="go"),
            AssistantMessage(
                content=[
                    ToolCallBlock(id="a", name="bash", input={}),
                    ToolCallBlock(id="b", name="bash", input={}),
                ]
            ),
            ToolResultMessage(tool_call_id="a", content=[TextBlock(text="ra")]),
            ToolResultMessage(tool_call_id="b", content=[TextBlock(text="rb")]),
            AssistantMessage(content=[TextBlock(text="done")]),
        ]
        out = convert_to_anthropic(messages)
        self.assertEqual([m["role"] for m in out], ["user", "assistant", "user", "assistant"])
        merged = out[2]["content"]
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["tool_use_id"], "a")

    def test_orphan_tool_result_dropped(self):
        messages = [
            UserMessage(content="go"),
            ToolResultMessage(tool_call_id="ghost", content=[TextBlock(text="r")]),
            AssistantMessage(content=[TextBlock(text="done")]),
        ]
        out = convert_to_anthropic(messages)
        # The orphan result is dropped, not sent.
        self.assertEqual(len(out), 2)
        self.assertEqual(out[1]["role"], "assistant")

    def test_orphan_tool_use_stripped(self):
        messages = [
            UserMessage(content="go"),
            AssistantMessage(content=[ToolCallBlock(id="never", name="bash", input={})]),
        ]
        out = convert_to_anthropic(messages)
        self.assertEqual(out[1]["role"], "assistant")
        self.assertEqual(out[1]["content"], [])

    def test_custom_message_becomes_user_with_prefix(self):
        messages = [CustomMessage(kind="compactionSummary", text="the summary")]
        out = convert_to_anthropic(messages)
        self.assertEqual(out[0]["role"], "user")
        self.assertIn("the summary", out[0]["content"])

    def test_first_message_always_user(self):
        messages = [AssistantMessage(content=[TextBlock(text="started mid-turn")])]
        out = convert_to_anthropic(messages)
        self.assertEqual(out[0]["role"], "user")
        self.assertIn("Continue", out[0]["content"])

    def test_image_block_mapping(self):
        from fruitfly_agent.core.data_model import ImageBlock

        messages = [UserMessage(content=[TextBlock(text="see"), ImageBlock(data="abc", media_type="image/png")])]
        out = convert_to_anthropic(messages)
        content = out[0]["content"]
        self.assertEqual(content[1]["type"], "image")
        self.assertEqual(content[1]["source"]["media_type"], "image/png")


if __name__ == "__main__":
    unittest.main()
