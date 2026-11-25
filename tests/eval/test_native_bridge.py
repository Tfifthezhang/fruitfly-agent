"""Every native host supplies full configuration rather than synthesized model flags."""
import shlex
import unittest
from pathlib import Path
import tempfile
from types import SimpleNamespace
from fruitfly_eval.bridges.native import NativeInvocation


class NativeBridgeTests(unittest.TestCase):
    def test_relay_mounts_are_private_to_trial_and_dependency_mounts_stay_read_only(self):
        from fruitfly_eval.backends.mounts import PreparedMounts
        from fruitfly_eval.bridges.model_access import trial_relay_directory
        from fruitfly_eval.harbor.model_access import TARGET
        class Host:
            def __init__(self, **kwargs): self.mounts = kwargs['mounts']
        class Environment(PreparedMounts, Host): pass
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relay = {'source': str(root / 'relay'), 'target': TARGET, 'read_only': False}
            paths = []
            for name in ('first', 'second'):
                trial = root / name
                environment = Environment(mounts=[relay], dependency_mounts=[{
                    'source': str(root / 'assets'), 'target': '/assets', 'read_only': True}],
                    trial_paths=SimpleNamespace(trial_dir=trial), session_id=name)
                expected = trial_relay_directory(root / 'relay', trial)
                self.assertEqual(environment.mounts[0]['source'], str(expected))
                self.assertEqual(expected.stat().st_mode & 0o777, 0o700)
                self.assertTrue(environment.mounts[1]['read_only'])
                paths.append(expected)
            self.assertNotEqual(*paths)
            self.assertEqual(relay['source'], str(root / 'relay'))

    def test_invocation_preserves_config_and_literal_instruction(self):
        instruction = 'Inspect `file` and $(do-not-execute); then explain.\nNext line.'
        invocation = NativeInvocation('/runtime/bin/python', 'selected profile', instruction,
            config='/frozen configuration/system.yaml')
        argv = invocation.argv()
        self.assertEqual(shlex.split(shlex.join(argv)), argv)
        self.assertEqual(argv[-2:], ['--', instruction])
        self.assertEqual(argv[argv.index('--config') + 1], '/frozen configuration/system.yaml')
        self.assertEqual(argv[argv.index('--profile') + 1], 'selected profile')
        self.assertEqual(argv[argv.index('--session') + 1], '/logs/agent/session.jsonl')
        self.assertNotIn('--model', argv)
        self.assertNotIn('--api-key', argv)

    def test_invalid_execution_paths_fail_before_launch(self):
        for path in ('python', '/runtime/../python', '/runtime/python\x00'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                NativeInvocation(path, 'baseline', 'Work')
