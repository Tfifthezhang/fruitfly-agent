"""Model access delivery and retirement without Docker or a real Provider."""

import asyncio
import json
import os
import stat
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fruitfly_agent.providers.auth.stores import read_private_json
from fruitfly_eval.harbor import access_files


class AccessFileTests(unittest.IsolatedAsyncioTestCase):
    def test_socket_permissions_preserve_owner_and_restrict_to_agent_group(self):
        endpoint = '/opt/fruitfly-model-relay/trial-fixture/model.sock'
        def info(path):
            return SimpleNamespace(st_uid=os.getuid(), st_mode=(stat.S_IFSOCK if path.name == 'model.sock' else stat.S_IFDIR))
        with patch.object(Path, 'lstat', info), patch.object(os, 'chown') as chown, patch.object(os, 'chmod') as chmod:
            access_files._grant_socket('1001', endpoint)
            self.assertEqual([c.args[1] for c in chown.call_args_list], [-1, -1, -1])
            self.assertEqual([c.args[2] for c in chown.call_args_list], [1001] * 3)
            self.assertEqual([c.args[1] for c in chmod.call_args_list], [0o710, 0o710, 0o660])
            for invalid in ('/etc/model.sock', '/opt/fruitfly-model-relay/../trial-x/model.sock',
                            '/opt/fruitfly-model-relay/trial-x/not-a-socket'):
                with self.assertRaises(ValueError):
                    access_files._grant_socket('1001', invalid)

    async def test_unix_publish_grants_socket_before_agent_probe(self):
        descriptor = {'models': {'fixture': {'socket': '/opt/fruitfly-model-relay/trial-x/model.sock'}}}
        async with access_files.ContainerModelAccess(self.agent, self.env) as files:
            await files.publish(descriptor, ca_source=None)
        calls = [c.kwargs['command'] for c in self.agent.exec_as_root.await_args_list]
        self.assertIn('grant-socket', calls[1])
        self.assertIn('1001', calls[1])

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.agent = SimpleNamespace(runtime_python='/python', runtime_environment={},
            exec_as_root=AsyncMock(), exec_as_agent=AsyncMock(return_value=SimpleNamespace(stdout='[1000, 1001]')))
        self.env = SimpleNamespace(upload_file=AsyncMock(), stop=AsyncMock())

    async def test_uses_actual_identity_and_publishes_private_material(self):
        descriptor = {'models': {'fixture': {'grant': 'private', 'ca': None}}}
        ca = self.root / 'ca.pem'
        ca.touch()
        async def upload(source, target):
            if target.endswith('.json'):
                self.assertEqual(source.stat().st_mode & 0o777, 0o600)
                self.assertEqual(json.loads(source.read_text())['models']['fixture']['ca'],
                                 str(Path(target).with_name('relay-ca.pem')))
        self.env.upload_file.side_effect = upload
        async with access_files.ContainerModelAccess(self.agent, self.env) as files:
            await files.publish(descriptor, ca_source=ca)
        self.assertIsNone(descriptor['models']['fixture']['ca'])
        calls = [call.kwargs['command'] for call in self.agent.exec_as_root.await_args_list]
        self.assertIn(f'publish {files.execution_id} 1000 1001 tls', calls[1])
        self.assertIn(f'remove {files.execution_id}', calls[2])
        self.assertNotEqual(files.directory, access_files.ContainerModelAccess(self.agent, self.env).directory)

    async def test_partial_upload_failure_retires_files(self):
        self.env.upload_file.side_effect = OSError('upload failed')
        with self.assertRaisesRegex(OSError, 'upload failed'):
            async with access_files.ContainerModelAccess(self.agent, self.env) as files:
                await files.publish({'models': {}}, ca_source=None)
        self.assertIn(' remove ', self.agent.exec_as_root.await_args.kwargs['command'])

    async def test_cancellation_drains_upload_before_deletion(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def upload(source, _target):
            started.set()
            await release.wait()
            self.assertTrue(source.exists())
        self.env.upload_file.side_effect = upload
        async def run():
            async with access_files.ContainerModelAccess(self.agent, self.env) as files:
                await files.publish({'models': {}}, ca_source=None)
        task = asyncio.create_task(run())
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        self.assertEqual(self.agent.exec_as_root.await_count, 1)
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIn(' remove ', self.agent.exec_as_root.await_args.kwargs['command'])

    async def test_cleanup_failure_preserves_primary_and_stops_environment(self):
        primary = ValueError('task failure')
        self.agent.exec_as_root.side_effect = [None, None, OSError('remove failed')]
        self.env.stop.side_effect = OSError('stop failed')
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed') as caught:
            async with access_files.ContainerModelAccess(self.agent, self.env) as files:
                await files.publish({'models': {}}, ca_source=None)
                raise primary
        self.assertIs(caught.exception.__cause__, primary)
        self.assertIn('Environment stop unconfirmed: OSError', caught.exception.__notes__)

    def test_wrong_owner_is_rejected_until_publish_repairs_it(self):
        directory_id = 'a' * 32
        uid = os.getuid()
        original_fstat = os.fstat
        uploaded_owner = uid + 1
        def chown(fd, new_uid, gid):
            nonlocal uploaded_owner
            uploaded_owner = new_uid
        def wrong_owner(fd):
            info = original_fstat(fd)
            return SimpleNamespace(st_mode=info.st_mode, st_uid=uploaded_owner, st_nlink=info.st_nlink)
        with patch.object(access_files, 'ROOT', self.root / 'access'), patch.object(
                access_files, '_trusted_directory'):
            access_files._operate('create', directory_id)
            path = access_files.ROOT / directory_id / 'model-access.json'
            path.write_text('{}')
            path.chmod(0o600)
            with patch.object(os, 'fstat', side_effect=wrong_owner):
                with self.assertRaisesRegex(ValueError, 'owner-only'):
                    read_private_json(path)
                with patch.object(os, 'fchown', side_effect=chown) as transfer, patch.object(os, 'chown'):
                    access_files._operate('publish', directory_id, str(uid), str(os.getgid()))
                    self.assertEqual(transfer.call_args.args[1:], (uid, os.getgid()))
                self.assertEqual(read_private_json(path), {})
            access_files._operate('remove', directory_id)
            self.assertFalse(path.exists())

    def test_publish_refuses_symlinks(self):
        with patch.object(access_files, 'ROOT', self.root / 'access'), patch.object(
                access_files, '_trusted_directory'):
            execution_id = 'b' * 32
            access_files._operate('create', execution_id)
            target = self.root / 'untouched'
            target.touch()
            (access_files.ROOT / execution_id / 'model-access.json').symlink_to(target)
            with self.assertRaises(OSError):
                access_files._operate('publish', execution_id, '0', '0')
            access_files._operate('remove', execution_id)
            self.assertTrue(target.exists())

    def test_tls_probe_checks_hostname_and_propagates_certificate_failure(self):
        descriptor = {'models': {'one': {
            'network_url': 'https://relay.example:1234', 'ca': '/fixture-ca',
        }}}
        path = self.root / 'access.json'
        path.write_text(json.dumps(descriptor))
        path.chmod(0o600)
        with patch('fruitfly_agent.providers.gateway.access.access_registry'), patch.object(
                access_files.ssl, 'create_default_context') as context, patch.object(
                access_files.socket, 'create_connection') as connect:
            access_files._probe(path)
            context.assert_called_once_with(cafile='/fixture-ca')
            connect.assert_called_once_with(('relay.example', 1234), timeout=3)
            wrap = context.return_value.wrap_socket
            wrap.assert_called_once_with(connect.return_value.__enter__.return_value,
                                         server_hostname='relay.example')
            wrap.side_effect = access_files.ssl.SSLCertVerificationError('fixture certificate')
            with self.assertRaises(access_files.ssl.SSLCertVerificationError):
                access_files._probe(path)
