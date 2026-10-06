"""Core data-model entry and message serialization contracts."""

import unittest
from dataclasses import FrozenInstanceError

from fruitfly_agent.core.data_model import (
    AssistantMessage,
    ContextDecision,
    ContextItem,
    ContextSnapshot,
    CustomMessage,
    ImageBlock,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolResultMessage,
    Usage,
    UserMessage,
    message_from_dict,
)


class TestRoundTrip(unittest.TestCase):
    def test_unified_entry_exports_message_and_runtime_models(self):
        import fruitfly_agent.core.data_model as data_model

        self.assertIn("AgentMessage", data_model.__all__)
        self.assertIn("AgentLoopContext", data_model.__all__)
        self.assertIs(data_model.UserMessage, UserMessage)

    def test_user_text(self):
        m = UserMessage(content="hello")
        self.assertEqual(message_from_dict(m.to_dict()), m)

    def test_user_blocks(self):
        m = UserMessage(content=[TextBlock("a"), ImageBlock(data="abc", media_type="image/png")])
        self.assertEqual(message_from_dict(m.to_dict()), m)

    def test_assistant_tool_calls(self):
        m = AssistantMessage(
            content=[
                ThinkingBlock("think"),
                TextBlock("let me check"),
                ToolCallBlock(id="call_1", name="bash", input={"command": "ls"}),
            ],
            stop_reason="toolUse",
            usage=Usage(input_tokens=100, output_tokens=20, cache_read_tokens=30),
        )
        self.assertEqual(message_from_dict(m.to_dict()), m)
        self.assertEqual(m.tool_calls[0].name, "bash")
        self.assertEqual(m.text, "let me check")

    def test_tool_result(self):
        m = ToolResultMessage(
            tool_call_id="call_1", content=[TextBlock("out")], is_error=True, terminate=False
        )
        self.assertEqual(message_from_dict(m.to_dict()), m)

    def test_custom(self):
        m = CustomMessage(kind="compactionSummary", text="summary here")
        self.assertEqual(message_from_dict(m.to_dict()), m)

    def test_unknown_stop_reason_normalized(self):
        d = AssistantMessage(content=[TextBlock("x")], stop_reason="stop").to_dict()
        d["stopReason"] = "weird-value"
        restored = message_from_dict(d)
        self.assertEqual(restored.stop_reason, "stop")  # type: ignore[union-attr]

    def test_unknown_role_raises(self):
        with self.assertRaises(ValueError):
            message_from_dict({"role": "alien"})

    def test_compaction_contract_is_an_immutable_snapshot_and_decision(self):
        message = UserMessage(content="task")
        snapshot = ContextSnapshot(
            canonical_items=(ContextItem(id="input:0", message=message),),
            messages=(message,),
            system_prompt="",
            tools=(),
            context_window=1000,
            model="test",
            max_tokens=100,
            trigger="budget",
        )
        decision = ContextDecision(messages=snapshot.messages, mechanism_id="test")

        self.assertIsInstance(snapshot.messages, tuple)
        self.assertEqual("input:0", snapshot.canonical_items[0].id)
        self.assertEqual((message,), decision.messages)
        with self.assertRaises(FrozenInstanceError):
            snapshot.model = "changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
