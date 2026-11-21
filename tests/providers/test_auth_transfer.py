"""Selected registration deployment never copies host state or logs credentials."""
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fruitfly_agent.providers.auth.stores import FileCredentialStore
from fruitfly_agent.providers.auth.transfer import deploy, receive, registration
from tests.support.connections import account_record


class AuthTransferTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.local = FileCredentialStore(self.root / 'local')
        self.remote = FileCredentialStore(self.root / 'remote')
        self.local.modify('account-a', lambda _: account_record())

    def test_only_selected_registration_is_published_without_touching_host_or_other_accounts(self):
        self.local.modify('unrelated', lambda _: account_record('unrelated'))
        self.remote.modify('server-account', lambda _: account_record('server-account'))
        host = self.root / 'host.json'
        host.write_text('{"id":"server-host"}')
        payload = registration(self.local, 'account-a')
        self.assertNotIn(b'unrelated', payload)
        self.assertEqual(receive(io.BytesIO(payload), self.remote, integrations=('chatgpt',)), 'account-a')
        self.assertEqual(self.remote.read('account-a'), self.local.read('account-a'))
        self.assertEqual(self.remote.read('server-account')['account'], 'server-account')
        self.assertEqual(host.read_text(), '{"id":"server-host"}')
        self.assertEqual(self.remote._path('account-a').stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            receive(io.BytesIO(payload), self.remote, integrations=('chatgpt',))
        self.local.modify('account-a', lambda value: {**value, 'access_token': 'replacement'})
        receive(io.BytesIO(registration(self.local, 'account-a')), self.remote, integrations=('chatgpt',), replace=True)
        self.assertEqual(self.remote.read('account-a')['access_token'], 'replacement')

    def test_invalid_and_oversized_transfers_leave_existing_registration_unchanged(self):
        original = account_record()
        self.remote.modify('account-a', lambda _: original)
        cases = [b'x' * (128 * 1024 + 1), b'{}', b'[]', b'{',
                 json.dumps({'registration': {**original, 'host_id': 'foreign'}}).encode(),
                 json.dumps({'registration': {**original, 'account': '../escape'}}).encode(),
                 json.dumps({'registration': {**original, 'integration': 'unknown'}}).encode()]
        for payload in cases:
            with self.subTest(payload_size=len(payload)):
                with self.assertRaises(ValueError):
                    receive(io.BytesIO(payload), self.remote, integrations=('chatgpt',), replace=True)
                self.assertEqual(self.remote.read('account-a'), original)

    def test_ssh_uses_stdin_and_fixed_command_without_exposing_remote_diagnostics(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
            deploy(self.local, 'account-a', 'user@server', python='/home/user/venv/bin/python')
        args, kwargs = run.call_args
        self.assertIn('BatchMode=yes', args[0])
        self.assertIn(b'offline-token-a', kwargs['input'])
        self.assertNotIn('offline-token-a', repr(args))
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 1, stderr=b'secret')):
            with self.assertRaises(ValueError) as raised:
                deploy(self.local, 'account-a', 'server')
        self.assertNotIn('secret', str(raised.exception))
        with patch('subprocess.run') as run:
            for host in ('-oProxyCommand=bad', 'server; command', 'host\ncommand'):
                with self.assertRaises(ValueError):
                    deploy(self.local, 'account-a', host)
            run.assert_not_called()

    def test_cli_headless_login_closes_attempt_and_never_prints_callback(self):
        import contextlib
        from fruitfly_agent.providers.auth.__main__ import main
        from unittest.mock import Mock
        attempt = Mock()
        service = Mock()
        service.begin_login.return_value = (attempt, 'https://example.test/authorize?state=fixture', {'account': 'a'})
        output = io.StringIO()
        with patch('fruitfly_agent.providers.connections.service.ConnectionService', return_value=service), patch(
                'getpass.getpass', return_value='http://localhost/callback?code=private-code'), contextlib.redirect_stdout(output):
            self.assertEqual(main(['login', 'chatgpt']), 0)
        attempt.accept.assert_called_once_with('http://localhost/callback?code=private-code')
        attempt.close.assert_called_once()
        service.complete_login.assert_called_once()
        self.assertNotIn('private-code', output.getvalue())

    def test_private_store_rejects_public_directory_lock_and_symlink_listing(self):
        directory = self.local.directory
        directory.chmod(0o755)
        with self.assertRaises(ValueError):
            self.local.read('account-a')
        directory.chmod(0o700)
        lock = self.local._path('account-a').with_suffix('.lock')
        lock.chmod(0o644)
        with self.assertRaises(ValueError):
            self.local.modify('account-a', lambda value: value)
        path = self.local._path('account-a')
        target = self.root / 'unowned-record.json'
        path.replace(target)
        path.symlink_to(target)
        self.assertEqual(self.local.list(), ())
