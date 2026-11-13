"""Session discovery behavior and failure contracts."""
from __future__ import annotations
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from fruitfly_agent.core.session import Session
from fruitfly_agent.run import resolve_session_path
from fruitfly_agent.run.application import discover_resumable_sessions
from tests.support.run import _args, _seed_resumable_session


class CliSurfaceTest(unittest.TestCase):
    def test_progressive_discovery_publishes_metadata_before_scanning_next_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('first', 'second'):
                _seed_resumable_session(root / '.fruitfly/sessions' / (name + '.jsonl'))
            updates = []
            inspected = []
            original = Session.inspect
            def inspect(path):
                if inspected:
                    self.assertEqual(1, len(updates))
                inspected.append(path)
                return original(path)
            with patch.object(Session, 'inspect', side_effect=inspect):
                result = discover_resumable_sessions(root, on_update=updates.append)
            self.assertEqual([1, 2], [len(items) for items in updates])
            self.assertEqual(result, updates[-1])

    def test_warm_discovery_avoids_body_reads_and_rechecks_writer_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / '.fruitfly/sessions/saved.jsonl'
            _seed_resumable_session(path)
            first = discover_resumable_sessions(root)
            with patch.object(Session, 'inspect', side_effect=AssertionError('warm discovery read history')):
                self.assertEqual(first, discover_resumable_sessions(root))
                with Session(path):
                    self.assertFalse(discover_resumable_sessions(root)[0].available)
                self.assertTrue(discover_resumable_sessions(root)[0].available)

    def test_modified_history_and_corrupt_cache_are_reinspected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / '.fruitfly/sessions/saved.jsonl'
            _seed_resumable_session(path)
            discover_resumable_sessions(root)
            cache = next((root / '.fruitfly/cache/session-index').glob('*.json'))
            for content in ('broken', '{}', '{"fingerprint":null}'):
                cache.write_text(content)
                self.assertTrue(discover_resumable_sessions(root)[0].available)
            with path.open('a') as stream:
                stream.write('{"id":999,"type":"meta"}\n')
            self.assertFalse(discover_resumable_sessions(root)[0].available)
            path.unlink()
            self.assertEqual((), discover_resumable_sessions(root))

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
