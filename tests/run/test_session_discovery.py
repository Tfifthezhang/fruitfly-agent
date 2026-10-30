"""Session discovery behavior and failure contracts."""
from __future__ import annotations
import os
import tempfile
import unittest
from pathlib import Path
from fruitfly_agent.core.session import Session
from fruitfly_agent.run import resolve_session_path
from fruitfly_agent.run.application import discover_resumable_sessions
from tests.support.run import _args, _seed_resumable_session


class CliSurfaceTest(unittest.TestCase):
    def test_resume_ignores_newer_manifest_only_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = _args()
            fresh = resolve_session_path(args, root)
            self.assertEqual(fresh.parent, root / ".fruitfly" / "sessions")
            self.assertRegex(fresh.name, r"^\d{8}T\d{6}Z-[0-9a-f]{8}\.jsonl$")

            sessions = root / ".fruitfly" / "sessions"
            sessions.mkdir(parents=True)
            older = sessions / "older.jsonl"
            newer = sessions / "newer.jsonl"
            _seed_resumable_session(older)
            _seed_resumable_session(newer, message=None)
            os.utime(older, ns=(1, 1))
            os.utime(newer, ns=(2, 2))
            args.resume = True
            self.assertEqual(resolve_session_path(args, root), older.resolve())

    def test_discovery_shows_changed_environments_and_locked_or_corrupt_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / ".fruitfly" / "sessions"
            current, changed, locked, corrupt = (sessions / f"{name}.jsonl" for name in ("current", "changed", "locked", "corrupt"))
            _seed_resumable_session(current)
            _seed_resumable_session(changed, digest="another-environment")
            _seed_resumable_session(locked)
            corrupt.write_text('{"id":1}\nnot json\n{"id":2}\n')
            before = {p: p.read_bytes() for p in (changed, locked, corrupt)}
            with Session(locked):
                found = {Path(item.path).name: item for item in discover_resumable_sessions(root, current_path=current)}
                self.assertEqual({"changed.jsonl", "locked.jsonl", "corrupt.jsonl"}, set(found))
                self.assertTrue(found["changed.jsonl"].available)
                self.assertEqual("offline-model", found["changed.jsonl"].model)
                self.assertFalse(found["locked.jsonl"].available)
                self.assertIn("locked", found["locked.jsonl"].reason)
                self.assertFalse(found["corrupt.jsonl"].available)
                self.assertIn("invalid", found["corrupt.jsonl"].reason)
            for p, contents in before.items():
                self.assertEqual(contents, p.read_bytes())
