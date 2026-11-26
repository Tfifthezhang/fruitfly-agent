"""Uploaded official test files stay readable by the non-root verifier user."""
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

try:  # Prefer the real optional SDK when it is installed (contract runs).
    from workbuddy_bench.runner.docker_environment import WorkBuddyDockerEnvironment
except ImportError:  # Offline double with the public upload/exec surface only.
    class WorkBuddyDockerEnvironment:  # type: ignore[no-redef]
        async def upload_file(self, source_path, target_path):
            raise AssertionError('test must patch the parent upload_file')

        async def exec(self, **kwargs):
            raise AssertionError('test must patch the parent exec')

    module = ModuleType('workbuddy_bench.runner.docker_environment')
    module.WorkBuddyDockerEnvironment = WorkBuddyDockerEnvironment
    sys.modules['workbuddy_bench.runner.docker_environment'] = module

from fruitfly_eval.workbuddy.environment import PreparedWorkBuddyEnvironment


class WorkBuddyEnvironmentUploadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.environment = PreparedWorkBuddyEnvironment.__new__(PreparedWorkBuddyEnvironment)

    def recorded(self, return_code=0):
        calls = []

        async def upload(parent, source_path, target_path):
            calls.append(('upload', source_path, target_path))

        async def execute(parent, **kwargs):
            calls.append(('exec', kwargs))
            return SimpleNamespace(return_code=return_code, stdout='', stderr='')

        return calls, patch.object(WorkBuddyDockerEnvironment, 'upload_file', upload), \
            patch.object(WorkBuddyDockerEnvironment, 'exec', execute)

    async def test_tests_upload_is_normalized_after_the_official_upload(self):
        calls, upload, execute = self.recorded()
        with upload, execute:
            await self.environment.upload_file('/tmp/transformed.py', '/tests/verifier.py')
        self.assertEqual(calls[0], ('upload', '/tmp/transformed.py', '/tests/verifier.py'))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][0], 'exec')
        options = calls[1][1]
        self.assertEqual(options['user'], 'root')
        self.assertIn('chmod 644', options['command'])
        self.assertIn(shlex.quote('/tests/verifier.py'), options['command'])

    async def test_upload_outside_tests_keeps_the_official_behavior(self):
        calls, upload, execute = self.recorded()
        with upload, execute:
            await self.environment.upload_file('/tmp/data.json', '/app/data.json')
        self.assertEqual(calls, [('upload', '/tmp/data.json', '/app/data.json')])

    async def test_traversal_target_is_rejected_before_any_upload(self):
        calls, upload, execute = self.recorded()
        with upload, execute:
            with self.assertRaises(ValueError):
                await self.environment.upload_file('/tmp/x.py', '/tests/../etc/passwd')
        self.assertEqual(calls, [])

    async def test_relative_target_is_rejected_before_any_upload(self):
        calls, upload, execute = self.recorded()
        with upload, execute:
            with self.assertRaises(ValueError):
                await self.environment.upload_file('/tmp/x.py', 'tests/verifier.py')
        self.assertEqual(calls, [])

    async def test_failed_normalization_raises_instead_of_silent_zero_reward(self):
        calls, upload, execute = self.recorded(return_code=1)
        with upload, execute:
            with self.assertRaises(RuntimeError):
                await self.environment.upload_file('/tmp/x.py', '/tests/verifier.py')
        self.assertEqual(calls[0][0], 'upload')
        self.assertEqual(calls[1][0], 'exec')

    async def test_host_source_file_mode_is_never_modified(self):
        calls, upload, execute = self.recorded()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'transformed.py'
            source.write_text('# transformed verifier')
            source.chmod(0o600)
            with upload, execute:
                await self.environment.upload_file(source, '/tests/verifier.py')
            self.assertEqual(source.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
