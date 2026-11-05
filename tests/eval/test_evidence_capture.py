"""Actual scoped file retention and public lifecycle bindings, without Docker."""
import asyncio
import json
from pathlib import Path
import tempfile
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fruitfly_eval.harbor.evidence_capture import capture, capture_policy
from fruitfly_eval.harbor.evidence_hooks import bind_capture, EvidenceCapturePlugin


class EvidenceCaptureTests(unittest.TestCase):
    def test_referenced_complete_tool_output_is_retained_with_its_actual_bytes(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.NamedTemporaryFile(prefix='fruitfly-bash-', suffix='.log', delete=False) as log:
            path = Path(log.name).resolve()
            try:
                log.write(b'complete tool output'); log.flush()
                root = Path(directory).resolve(); work = root / 'work'; work.mkdir()
                destination = root / 'agent/evidence-capture'; destination.parent.mkdir()
                (destination.parent / 'session.jsonl').write_text(json.dumps({'message': {
                    'role': 'toolResult', 'details': {'full_output_path': str(path)}, 'content': []}}) + '\n')
                capture(work, destination, phase='baseline')
                with patch('fruitfly_eval.harbor.evidence_capture.tempfile.gettempdir', return_value=str(path.parent)):
                    value = capture(work, destination)
                entry = next(r for r in value['files'] if r['status'] == 'collected')
                self.assertTrue(entry['archive_path'].startswith('tool-output/'))
                self.assertEqual((destination / entry['archive_path']).read_bytes(), b'complete tool output')
            finally:
                path.unlink(missing_ok=True)

    def test_file_mutation_during_copy_is_not_reported_as_a_stable_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); work = root / 'work'; work.mkdir()
            answer = work / 'answer'; answer.write_text('before')
            capture(work, root / 'saved', phase='baseline')
            answer.write_text('after')
            original, calls = os.fstat, 0
            def fstat(fd):
                nonlocal calls
                calls += 1
                if calls == 2:
                    value = answer.stat()
                    os.utime(answer, ns=(value.st_atime_ns, value.st_mtime_ns + 1000000))
                return original(fd)
            with patch('fruitfly_eval.harbor.evidence_capture.os.fstat', side_effect=fstat):
                value = capture(work, root / 'saved')
            self.assertEqual(value['status'], 'partial')
            self.assertEqual(value['files'][0]['status'], 'collection_failed')

    def test_changed_deleted_and_explicit_unchanged_files_are_captured_before_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work, saved = root / 'work', root / 'saved'
            work.mkdir()
            (work / 'unchanged.txt').write_text('constant')
            (work / 'changed.txt').write_text('before')
            (work / 'deleted.txt').write_text('remove')
            policy = {'extra_paths': ['unchanged.txt']}
            capture(work, saved, policy, phase='baseline')
            (work / 'changed.txt').write_text('agent output')
            (work / 'created.bin').write_bytes(b'\x00\xff\x01')
            (work / 'deleted.txt').unlink()
            receipt = capture(work, saved, policy)
            (work / 'changed.txt').write_text('verifier mutation')
            rows = {Path(r['path']).name: r for r in receipt['files']}
            self.assertEqual(receipt['status'], 'complete')
            self.assertEqual(rows['unchanged.txt']['status'], 'collected')
            self.assertEqual(rows['deleted.txt']['status'], 'deleted')
            self.assertEqual((saved / rows['changed.txt']['archive_path']).read_text(), 'agent output')
            self.assertEqual((saved / rows['created.bin']['archive_path']).read_bytes(), b'\x00\xff\x01')

    def test_limits_failures_and_symlinks_are_explicit_and_secrets_are_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); work = root / 'work'; work.mkdir()
            outside = root / 'private'; outside.write_text('outside')
            (work / 'escape').symlink_to(outside)
            (work / '.env').write_text('SECRET FIXTURE')
            (work / 'large').write_text('12345')
            saved = root / 'saved'
            capture(work, saved, {'max_file_bytes': 4}, phase='baseline')
            value = capture(work, saved, {'max_file_bytes': 4})
            self.assertEqual(value['status'], 'partial')
            self.assertTrue(any(r['reason'] == 'byte limit' for r in value['files'] if 'reason' in r))
            self.assertTrue(any(r.get('reason') == 'symlink' for r in value['files']))
            self.assertFalse(any(Path(r['path']).name == '.env' for r in value['files']))
            self.assertFalse(any(p.is_file() and p.read_bytes() == b'outside' for p in saved.rglob('*')))
            for policy in ({'unknown': 1}, {'max_file_bytes': True}, {'include_tool_outputs': 1}):
                with self.subTest(policy=policy), self.assertRaises(ValueError):
                    capture_policy(policy)

    def test_capture_without_baseline_cannot_claim_full_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); work = root / 'work'; work.mkdir()
            (work / 'answer').write_text('answer')
            value = capture(work, root / 'saved')
            self.assertEqual(value['status'], 'partial')
            self.assertEqual(value['baseline_status'], 'unknown')
            self.assertEqual(value['files'][0]['status'], 'collected')


class EvidenceHookTests(unittest.IsolatedAsyncioTestCase):
    async def test_job_hooks_use_installed_capabilities_and_release_each_trial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); trial = root / 'trial'
            execute = AsyncMock(return_value=SimpleNamespace(return_code=0))
            download = AsyncMock()
            bind_capture(trial, python='/prepared/python', policy={}, execute=execute, download=download)
            registrations = {}
            job = SimpleNamespace(job_dir=root,
                on_agent_started=lambda cb: registrations.update(start=cb),
                on_agent_ended=lambda cb: registrations.update(end=cb),
                on_trial_ended=lambda cb: registrations.update(release=cb),
                on_trial_cancelled=lambda cb: registrations.update(cancel=cb))
            plugin = EvidenceCapturePlugin(); await plugin.on_job_start(job)
            event = SimpleNamespace(config=SimpleNamespace(trials_dir=root, trial_name='trial'))
            await registrations['start'](event)
            await registrations['end'](event)
            self.assertIn('--phase baseline', execute.await_args_list[0].args[0])
            self.assertIn('--phase final', execute.await_args_list[1].args[0])
            self.assertEqual(download.await_count, 2)
            await registrations['release'](event)
            await registrations['end'](event)
            self.assertEqual(execute.await_count, 2)
            receipt = json.loads((trial / 'agent/evidence-capture/manifest.json').read_text())
            self.assertEqual(receipt['status'], 'partial')
            await plugin.on_job_end(None)
