"""Session retains concise outcomes for successful and failed Agent runs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.session import Session

from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_config


class SessionRunRecordTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_records_run_bounds_and_keeps_messages_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = FauxProvider()
            provider.respond_text("answer")
            with Session(Path(directory) / "session.jsonl") as session:
                result = await run_agent_loop(
                    make_config(provider, session=session),
                    [UserMessage(content="question")],
                )
                records = [
                    entry.payload for entry in session.read_all()
                    if entry.type == "meta" and entry.payload.get("kind") == "runRecord"
                ]
                events = [item["event"] for item in records]

                self.assertFalse(result.is_error)
                self.assertEqual(["start", "request_context", "request_receipt", "end"], events)
                self.assertEqual(records[0]["run_id"], records[-1]["run_id"])
                end = records[-1]["data"]
                self.assertEqual("stop", end["stop_reason"])
                self.assertEqual(1, end["provider_attempt_count"])
                self.assertEqual(0, end["provider_failure_count"])
                self.assertEqual(["question", "answer"], [
                    getattr(item, "text", getattr(item, "content", ""))
                    for item in session.canonical_messages()
                ])

    async def test_provider_failure_is_summarized_without_copying_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = FauxProvider()
            provider.respond_fatal("provider offline " + "x" * 700)
            with Session(Path(directory) / "session.jsonl") as session:
                result = await run_agent_loop(
                    make_config(provider, session=session),
                    [UserMessage(content="private prompt")],
                )
                records = [
                    entry.payload for entry in session.read_all()
                    if entry.type == "meta" and entry.payload.get("kind") == "runRecord"
                ]

                self.assertTrue(result.is_error)
                self.assertEqual(
                    ["start", "request_context", "provider_attempt_failed", "end"],
                    [item["event"] for item in records],
                )
                failure = records[2]["data"]
                self.assertEqual("FatalError", failure["error_kind"])
                self.assertEqual("terminal", failure["disposition"])
                self.assertLessEqual(len(failure["error"]), 513)
                self.assertNotIn("messages", failure)
                self.assertNotIn("system_prompt", failure)
                self.assertEqual("private prompt", session.canonical_messages()[0].content)


if __name__ == "__main__":
    unittest.main()
