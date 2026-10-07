"""Canonical history snapshots and static terminal presentation."""

import io
import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import (
    AssistantMessage, ImageBlock, TextBlock, ThinkingBlock, ToolCallBlock,
    ToolResultMessage, UserMessage,
)
from fruitfly_agent.core.session import Session
from fruitfly_agent.interactive import InteractiveSession, TerminalRenderer
from tests.support.application import offline_session
from tests.support.faux_provider import FauxProvider
from tests.support.terminal import TtyStringIO


class ConversationTest(unittest.IsolatedAsyncioTestCase):
    async def test_history_uses_original_messages_after_context_reduction(self):
        original = [UserMessage("original question"), AssistantMessage([TextBlock("original answer")])]
        projection = [UserMessage("context summary only")]
        with tempfile.TemporaryDirectory() as tmp, Session(Path(tmp) / "session.jsonl") as durable:
            for message in original:
                durable.append("message", {"message": message.to_dict()})
            durable.append("compaction", {"messages": [m.to_dict() for m in projection]})
            session = InteractiveSession(
                AgentLoopConfig(provider=FauxProvider(), model="offline", session=durable),
                messages=durable.messages(),
            )
            before = durable.read_all()
            snapshot = session.conversation()
            self.assertEqual([m.content[0].text for m in snapshot], ["original question", "original answer"])
            self.assertEqual(session.messages, projection)
            self.assertEqual(durable.read_all(), before)
            with self.assertRaises(FrozenInstanceError):
                snapshot[0].content[0].text = "changed"

    async def test_snapshot_and_display_preserve_block_order_without_private_payloads(self):
        messages = [
            UserMessage([TextBlock("question"), ImageBlock("PRIVATE_IMAGE_BYTES", "image/png")]),
            AssistantMessage([
                ThinkingBlock("PRIVATE_REASONING"), TextBlock("before "), TextBlock("call"),
                ToolCallBlock("call-1", "echo", {"api_key": "PRIVATE_ARGUMENT"}), TextBlock("after call"),
            ]),
            ToolResultMessage("call-1", [TextBlock("x" * 1000), ImageBlock("RESULT_BYTES", "image/png")], is_error=True),
        ]
        session = offline_session(messages=messages)
        for tty in (False, True):
            with self.subTest(tty=tty), patch.dict(os.environ, {"TERM": "xterm", "NO_COLOR": "1"}):
                output = TtyStringIO() if tty else io.StringIO()
                renderer = TerminalRenderer(output)
                await renderer.show_history(session.conversation())
                await renderer.close()
                text = output.getvalue()
                for hidden in ("PRIVATE_IMAGE_BYTES", "PRIVATE_REASONING", "PRIVATE_ARGUMENT", "RESULT_BYTES"):
                    self.assertNotIn(hidden, text)
                self.assertIn("Image attachment · image/png", text)
                self.assertIn("Reasoning omitted", text)
                self.assertIn("Tool · echo (error)", text)
                self.assertIn("historical tool output truncated", text)
                self.assertNotIn("x" * 801, text)
                self.assertLess(text.index("before call"), text.index("Tool call · echo"))
                self.assertLess(text.index("Tool call · echo"), text.index("after call"))
                self.assertNotIn("\x1b", text)
        self.assertEqual(session.messages, messages)
        self.assertEqual(session.trace(), [])

    async def test_markdown_controls_and_empty_history(self):
        messages = [UserMessage("hello\x1b[2J"), AssistantMessage([TextBlock("**answer**\n\n```python\nprint('ok')\n```\n")])]
        for tty in (False, True):
            with self.subTest(tty=tty), patch.dict(os.environ, {"TERM": "xterm", "NO_COLOR": "1"}):
                output = TtyStringIO() if tty else io.StringIO()
                renderer = TerminalRenderer(output)
                await renderer.show_history(())
                self.assertEqual(output.getvalue(), "")
                await renderer.show_history(offline_session(messages=messages).conversation())
                await renderer.close()
                text = output.getvalue()
                self.assertIn("answer", text)
                self.assertIn("print('ok')", text)
                self.assertIn("hello\\x1b[2J", text)
                self.assertNotIn("\x1b", text)
