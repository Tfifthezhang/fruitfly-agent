"""Session JSONL invariants: replay, torn tail, idempotency, locking."""

import json
import tempfile
import unittest
from pathlib import Path

from fruitfly_agent.core.errors import SessionCorruptError
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.data_model import (
    AssistantMessage,
    TextBlock,
    ToolResultMessage,
    UserMessage,
)


def _msg_entry(message) -> dict:
    """The payload dict passed to Session.append for a message entry."""
    return {"message": message.to_dict()}


class TestSession(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "session.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_replay_round_trip(self):
        with Session(self.path) as s:
            s.append("message", _msg_entry(UserMessage(content="hi")))
            s.append("message", _msg_entry(AssistantMessage(content=[TextBlock("hey")])))
        with Session(self.path) as s:
            entries = s.read_all()
            self.assertEqual([e.id for e in entries], [1, 2])
            messages = s.messages()
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0], UserMessage(content="hi"))

    def test_torn_tail_discarded(self):
        with Session(self.path) as s:
            s.append("message", _msg_entry(UserMessage(content="a")))
            s.append("message", _msg_entry(UserMessage(content="b")))
        # Simulate a torn append: garbage partial line at the end.
        with self.path.open("a") as f:
            f.write('{"id": 3, "type": "message", "payload": {"message": {"role": "u')
        with Session(self.path) as s:
            self.assertEqual([e.id for e in s.read_all()], [1, 2])

    def test_missing_trailing_newline_repaired(self):
        with Session(self.path) as s:
            s.append("message", _msg_entry(UserMessage(content="a")))
        with self.path.open("ab") as f:
            f.write(b'{"id": 2, "type": "message", "payload": {"message": {"role": "user", "content": "b"}}}')
        # No trailing newline — next append must repair, not corrupt.
        with Session(self.path) as s:
            s.append("message", _msg_entry(UserMessage(content="c")))
            self.assertEqual([e.id for e in s.read_all()], [1, 2, 3])

    def test_idempotent_provisioned_id(self):
        with Session(self.path) as s:
            e1 = s.append("message", _msg_entry(UserMessage(content="a")), entry_id=1)
            e2 = s.append("message", _msg_entry(UserMessage(content="a")), entry_id=1)
            self.assertEqual(e1.id, e2.id)
            self.assertEqual(len(s.read_all()), 1)

    def test_non_consecutive_seq_rejected(self):
        with Session(self.path) as s:
            s.append("message", _msg_entry(UserMessage(content="a")))
        with self.path.open("a") as f:
            f.write(json.dumps({"id": 5, "type": "meta"}) + "\n")
        with self.assertRaises(SessionCorruptError):
            Session(self.path)

    def test_load_failure_releases_file_lock(self):
        self.path.write_text('{"id": 2, "type": "meta"}\n', encoding="utf-8")
        with self.assertRaises(SessionCorruptError):
            Session(self.path)

        self.path.write_text('{"id": 1, "type": "meta"}\n', encoding="utf-8")
        with Session(self.path) as session:
            self.assertEqual([entry.id for entry in session.read_all()], [1])

    def test_duplicate_id_rejected(self):
        with self.path.open("w") as f:
            f.write(json.dumps({"id": 1, "type": "meta"}) + "\n")
            f.write(json.dumps({"id": 1, "type": "meta"}) + "\n")
        with self.assertRaises(SessionCorruptError):
            Session(self.path)

    def test_invalid_parent_rejected(self):
        with self.path.open("w") as f:
            f.write(json.dumps({"id": 1, "type": "meta"}) + "\n")
            f.write(json.dumps({"id": 2, "parentId": 1, "type": "meta"}) + "\n")
            f.write(json.dumps({"id": 3, "parentId": 3, "type": "meta"}) + "\n")
        with self.assertRaises(SessionCorruptError):
            Session(self.path)

    def test_invalid_append_leaves_disk_and_replay_unchanged(self):
        with Session(self.path) as session:
            first = session.append("meta", {"kind": "fixture"})
            before = self.path.read_bytes()
            for parent_id in (0, -1, 2, 999, True, 1.5, "1"):
                with self.subTest(parent_id=parent_id), self.assertRaises(SessionCorruptError):
                    session.append("meta", {}, parent_id=parent_id)
                self.assertEqual(before, self.path.read_bytes())
                self.assertEqual([first], session.read_all())
            session.append("meta", {}, parent_id=first.id)
        with Session(self.path) as session:
            self.assertEqual([None, 1], [entry.parent_id for entry in session.read_all()])

    def test_first_provisioned_id_must_start_at_one(self):
        with Session(self.path) as session:
            with self.assertRaises(SessionCorruptError):
                session.append("meta", {}, entry_id=5)
            self.assertEqual([], session.read_all())
            session.append("meta", {})
        with Session(self.path) as session:
            self.assertEqual([1], [entry.id for entry in session.read_all()])

    def test_flock_blocks_second_open(self):
        with Session(self.path):
            with self.assertRaises(SessionCorruptError):
                Session(self.path)

    def test_compaction_projection(self):
        with Session(self.path) as s:
            s.append("message", _msg_entry(UserMessage(content="old")))
            s.append(
                "compaction",
                {
                    "summary": "did things",
                    "retainedTail": [UserMessage(content="recent").to_dict()],
                    "tokensBefore": 100,
                },
            )
            s.append("message", _msg_entry(AssistantMessage(content=[TextBlock("after")])))
        with Session(self.path) as s:
            messages = s.messages()
            # compaction replaces everything before it: summary + retained tail
            # and messages appended after that snapshot remain replayable.
            self.assertEqual(len(messages), 3)
            self.assertEqual(messages[0].role, "custom")
            self.assertEqual(messages[0].text, "did things")  # type: ignore[union-attr]
            self.assertEqual(messages[1], UserMessage(content="recent"))
            self.assertEqual(messages[2], AssistantMessage(content=[TextBlock("after")]))

    def test_generic_projection_does_not_replace_canonical_transcript(self):
        old = UserMessage(content="old")
        recent = UserMessage(content="recent")
        projected = UserMessage(content="projected")
        with Session(self.path) as s:
            first = s.append("message", _msg_entry(old))
            second = s.append("message", _msg_entry(recent))
            s.append(
                "compaction",
                {
                    "messages": [projected.to_dict()],
                    "tokensBefore": 10,
                    "mechanismId": "test",
                    "trigger": "budget",
                    "metadata": {},
                },
                sync=True,
            )

            self.assertEqual([projected], s.messages())
            self.assertEqual([old, recent], s.canonical_messages())
            self.assertEqual(
                [f"session:{first.id}", f"session:{second.id}"],
                [item.id for item in s.context_items()],
            )


if __name__ == "__main__":
    unittest.main()
