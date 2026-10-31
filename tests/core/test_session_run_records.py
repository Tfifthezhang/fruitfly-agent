"""Session retains concise outcomes for successful and failed Agent runs."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from fruitfly_agent.core.data_model import Usage, UserMessage
from fruitfly_agent.core.extensions.hooks import AFTER_RESPONSE, HookRegistry
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.errors import RetryableError

from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_config, make_tool


class SessionRunRecordTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_failure_diagnostics_survive_result_and_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            diagnostics = {'causes': [{'type': 'ConnectionRefusedError', 'category': 'connection_refused'}]}
            def provider(view, *, signal=None):
                raise RetryableError('Connection error.', details={'diagnostics': diagnostics})
            with Session(Path(directory) / 'session.jsonl') as session:
                result = await run_agent_loop(make_config(provider, session=session), [UserMessage(content='go')])
                self.assertEqual(diagnostics, result.error_details['diagnostics'])
                records = [entry.payload for entry in session.read_all() if entry.payload.get('kind') == 'runRecord']
                self.assertEqual(diagnostics, next(r['data']['diagnostics'] for r in records if r['event'] == 'provider_attempt_failed'))
                self.assertEqual(diagnostics, records[-1]['data']['error']['diagnostics'])

    async def test_hook_adjusted_receipts_are_persisted_before_response_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = FauxProvider()
            provider.respond_tool_call("count", {"value": "one"})
            provider.respond_text("done")
            usage = [Usage(3, 2, 1, 4), None]
            observed = []
            hooks = HookRegistry()
            with Session(Path(directory) / "session.jsonl") as session:
                def adjust(event):
                    event.assistant = replace(event.assistant, usage=usage.pop(0))

                def observe(event):
                    receipts = [entry.payload["data"] for entry in session.read_all()
                                if entry.type == "meta" and entry.payload.get("event") == "request_receipt"]
                    self.assertEqual(event.receipt_timestamp, receipts[-1]["timestamp"])
                    observed.append(receipts[-1]["input_tokens"])
                    self.assertEqual(event.assistant, session.canonical_messages()[-1])

                hooks.add(AFTER_RESPONSE, adjust)
                hooks.on(AFTER_RESPONSE, observe)
                result = await run_agent_loop(make_config(provider, [make_tool()[0]],
                    session=session, hooks=hooks), [UserMessage(content="go")])
                self.assertFalse(result.is_error)
                self.assertEqual([3, None], observed)
                self.assertEqual(Usage(3, 2, 1, 4), result.usage)

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
