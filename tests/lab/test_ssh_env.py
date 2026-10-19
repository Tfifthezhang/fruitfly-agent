"""Offline SSH filesystem, transport, supervision and permission behavior."""
import asyncio
import errno
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fruitfly_agent.core.env import ExecOptions
from fruitfly_agent.core.tool_runtime.authorization import AuthorizationRequest, ToolPermission
from fruitfly_agent.lab.catalog import PermissionPolicy, builtin_catalog, MechanismSelection
from fruitfly_agent.lab.environment.ssh import SshConfig, SshEnv
from tests.support.ssh import SftpFixture, ProcessChannel


class SshEnvironmentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.env = SshEnv(SshConfig(host='server.example', port=2222, cwd='/srv/project'),
                          username='fixture-private-account', password='fixture-private-password')
        self.sftp = SftpFixture(self.root)
        self.sftp.path('/srv/project').mkdir(parents=True)
        self.env._sftp = self.sftp
        self.addAsyncCleanup(self.env.close)

    async def test_filesystem_protocol_including_links_new_paths_and_temporary_files(self):
        self.assertEqual('/srv/project/a', self.env.absolute_path('a').unwrap())
        self.assertEqual('/srv/project/a', self.env.join_path(['/srv/project', 'a']).unwrap())
        self.assertTrue(self.env.write_file('a/b.txt', 'hello').is_ok)
        self.assertTrue(self.env.append_file('a/b.txt', ' world').is_ok)
        self.assertEqual('hello world', self.env.read_text_file('a/b.txt').unwrap())
        self.assertTrue(self.env.write_file('bytes', b'\xff\x00').is_ok)
        self.assertEqual(b'\xff\x00', self.env.read_binary_file('bytes').unwrap())
        self.assertEqual(['b.txt'], [f.name for f in self.env.list_dir('a').unwrap()])
        self.sftp.path('/srv/project/link').symlink_to('a', target_is_directory=True)
        self.assertEqual('symlink', self.env.file_info('link').unwrap().kind)
        self.assertEqual('/srv/project/a/new/child', self.env.canonical_path('link/new/child').unwrap())
        self.assertEqual('/srv/project/new', self.env.canonical_path('link/../new').unwrap())
        self.assertTrue(self.env.rename_file('bytes', 'renamed').is_ok)
        self.assertTrue(self.env.exists('renamed').unwrap())
        self.assertFalse(self.env.exists('absent').unwrap())
        self.assertTrue(self.env.create_dir('one').is_ok)
        self.assertFalse(self.env.create_dir('absent/child', recursive=False).is_ok)
        for result in (self.env.create_temp_file(prefix='log-', suffix='.txt'), self.env.create_temp_dir()):
            self.assertTrue(result.is_ok, result.error)
            self.assertTrue(result.unwrap().startswith('/srv/project/.fruitfly/tmp/'))
        self.assertFalse(self.env.create_temp_file(prefix='../bad').is_ok)
        self.assertTrue(self.env.remove('a', recursive=True).is_ok)
        self.assertTrue(self.env.remove('missing').is_ok)
        self.assertFalse(self.env.read_text_file('a/b.txt').is_ok)
        self.assertFalse(self.env.write_file('bad\x00path', '').is_ok)

    async def test_symlink_loops_and_permission_errors_fail_closed_without_transport_details(self):
        self.sftp.path('/srv/project/loop').symlink_to('loop')
        self.assertFalse(self.env.canonical_path('loop').is_ok)
        leak = 'fixture-private-account fixture-private-password'
        with patch.object(self.sftp, 'stat', side_effect=OSError(errno.EACCES, leak)):
            result = self.env.exists('private')
        self.assertFalse(result.is_ok)
        self.assertNotIn('fixture-private', result.error)
        self.assertNotIn('fixture-private', repr(self.env))

    async def test_remote_permissions_use_remote_links_and_never_local_extra_roots(self):
        prompts = []
        async def confirm(prompt, signal):
            prompts.append(prompt)
            return 'once'
        policy = PermissionPolicy(self.root, read_roots=(Path('/etc'),), write_roots=(Path('/etc'),))
        guarded, authorizer = self.env.with_permissions(policy, confirm=confirm)
        self.assertEqual('/srv/project', guarded.cwd)
        self.assertTrue(guarded.write_file('note', 'remote').is_ok)
        self.sftp.path('/srv/project/.env').write_text('fixture')
        self.sftp.path('/srv/project/alias').symlink_to('.env')
        self.sftp.path('/etc').mkdir()
        self.sftp.path('/etc/allowed').write_text('external')
        self.sftp.path('/etc/other').write_text('other')
        for name in ('.env', 'alias', '.ssh/config', '.fruitfly/secrets.env'):
            self.assertFalse(guarded.read_text_file(name).is_ok)
            request = AuthorizationRequest('read', 'read', {'path': name}, ToolPermission('read', ('path',)))
            async with authorizer.authorize(request) as decision:
                self.assertFalse(decision.allowed)
        self.assertFalse(guarded.read_text_file('/etc/allowed').is_ok)
        link = self.sftp.path('/srv/project/external')
        link.symlink_to('/etc/allowed')
        request = AuthorizationRequest('read', 'read', {'path': 'external'}, ToolPermission('read', ('path',)))
        async with authorizer.authorize(request) as decision:
            self.assertTrue(decision.allowed)
            self.assertEqual('external', guarded.read_text_file('external').unwrap())
            self.assertFalse(guarded.read_text_file('/etc/other').is_ok)
            link.unlink()
            link.symlink_to('/etc/other')
            self.assertFalse(guarded.read_text_file('external').is_ok)
        self.assertFalse(guarded.read_text_file('/etc/allowed').is_ok)
        self.assertEqual(('/etc/allowed',), prompts[0].targets)
        self.assertTrue(guarded.create_temp_file().is_ok)
        events = []
        request = AuthorizationRequest('exec', 'bash', {'command': 'echo ok'}, ToolPermission('execute'))
        self.env.exec = Mock()
        async def execute(command, options):
            events.append(options)
            return None
        self.env.exec.side_effect = execute
        self.assertFalse((await guarded.exec('echo ok')).is_ok)
        async with authorizer.authorize(request) as decision:
            self.assertTrue(decision.allowed)
            await guarded.exec('echo ok')
            self.assertFalse((await guarded.exec('other')).is_ok)
        self.assertFalse(events[0].inherit_env)
        self.assertEqual({}, events[0].env)
        self.assertIn('server.example:2222', prompts[-1].session_label)

    def process_backend(self):
        self.env.cwd = str(self.root)
        channels = []
        def open_session(**kwargs):
            channel = ProcessChannel()
            channels.append(channel)
            return channel
        transport = Mock(open_session=open_session, is_active=lambda: True)
        self.env._client = Mock(get_transport=lambda: transport)
        return channels

    async def test_actual_supervisor_streams_output_and_quotes_command_directory_and_environment(self):
        channels = self.process_backend()
        updates = []
        async def callback(chunk):
            updates.append(chunk)
            if len(updates) == 1:
                raise RuntimeError('ordinary callback failure')
        command = "printf '你好'; printf 'error' >&2; sleep .1; printf \"%s\" \"$VALUE\"; exit 7"
        with patch.dict(os.environ, {'HOST_SECRET': 'fixture-host-secret'}):
            result = await self.env.exec(command, ExecOptions(inherit_env=False, env={'VALUE': "space ' $()"}, on_stdout=callback))
        self.assertTrue(result.is_ok, result.error)
        self.assertEqual("你好space ' $()", result.unwrap().stdout)
        self.assertEqual('error', result.unwrap().stderr)
        self.assertEqual(7, result.unwrap().exit_code)
        self.assertGreaterEqual(len(updates), 2)
        self.assertTrue(channels[0].closed)
        result = await self.env.exec('printf "%s" "${HOST_SECRET-unset}"', ExecOptions(inherit_env=False))
        self.assertEqual('unset', result.unwrap().stdout)

    async def test_timeout_and_task_cancellation_kill_remote_process_group(self):
        channels = self.process_backend()
        command = "(sleep .7; echo escaped > survived) & wait"
        result = await self.env.exec(command, ExecOptions(timeout_seconds=.15))
        self.assertTrue(result.is_ok, result.error)
        self.assertTrue(result.unwrap().cancelled)
        task = asyncio.create_task(self.env.exec(command))
        await asyncio.sleep(.15)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.sleep(.8)
        self.assertFalse((self.root / 'survived').exists())
        self.assertTrue(all(channel.closed for channel in channels))

    async def test_timeout_still_works_when_child_closes_both_output_streams(self):
        self.process_backend()
        result = await asyncio.wait_for(self.env.exec('exec >/dev/null 2>&1; sleep 10',
            ExecOptions(timeout_seconds=.1)), 2)
        self.assertTrue(result.is_ok, result.error)
        self.assertTrue(result.unwrap().cancelled)

    async def test_server_deadline_stops_command_without_client_cancellation(self):
        channel = ProcessChannel()
        self.addCleanup(channel.close)
        payload = {'command': 'exec >/dev/null 2>&1; sleep 10', 'cwd': str(self.root),
                   'env': {}, 'inherit_env': False, 'timeout': .1}
        import json
        import shlex
        from fruitfly_agent.lab.environment.ssh.supervisor import PROGRAM
        channel.exec_command('python3 -u -c ' + shlex.quote(PROGRAM) + ' ' + shlex.quote(json.dumps(payload)))
        for _ in range(100):
            if channel.exit_status_ready():
                break
            await asyncio.sleep(.01)
        self.assertTrue(channel.exit_status_ready())
        self.assertEqual(137, channel.recv_exit_status())

    async def test_missing_exit_status_is_failure_and_channel_is_closed(self):
        channel = Mock()
        channel.recv_ready.return_value = channel.recv_stderr_ready.return_value = False
        channel.exit_status_ready.return_value = True
        channel.recv_exit_status.return_value = -1
        transport = Mock()
        transport.open_session.return_value = channel
        self.env._client = Mock(get_transport=lambda: transport)
        result = await self.env.exec('echo x')
        self.assertFalse(result.is_ok)
        channel.close.assert_called_once()

    async def test_connection_is_password_only_verified_and_cleanup_is_idempotent(self):
        env = SshEnv(self.env.config, username='fixture-private-account', password='fixture-private-password')
        client, sftp = Mock(), Mock()
        sftp.stat.return_value.st_mode = 0o40700
        client.open_sftp.return_value = sftp
        fake = SimpleNamespace(SSHClient=Mock(return_value=client), RejectPolicy=Mock(return_value='reject'))
        with patch.dict(sys.modules, paramiko=fake):
            await env.start()
            await env.start()
        client.load_host_keys.assert_called_once()
        client.set_missing_host_key_policy.assert_called_once_with('reject')
        options = client.connect.call_args.kwargs
        self.assertEqual(2222, options['port'])
        self.assertFalse(options['allow_agent'])
        self.assertFalse(options['look_for_keys'])
        self.assertEqual('fixture-private-account', options['username'])
        await env.close()
        await env.close()
        client.close.assert_called_once()
        self.assertEqual('', env._password)

    async def test_failed_and_cancelled_start_close_connections_without_exposing_credentials(self):
        for cancelled in (False, True):
            env = SshEnv(self.env.config, username='fixture-private-account', password='fixture-private-password')
            client = Mock()
            client.load_host_keys.side_effect = RuntimeError('fixture-private-account fixture-private-password')
            fake = SimpleNamespace(SSHClient=lambda: client, RejectPolicy=Mock())
            if not cancelled:
                with patch.dict(sys.modules, paramiko=fake):
                    with self.assertRaises(RuntimeError) as raised:
                        await env.start()
                self.assertNotIn('fixture-private', str(raised.exception))
                client.close.assert_called_once()
            else:
                entered, release = threading.Event(), threading.Event()
                sftp = Mock()
                def connect():
                    entered.set()
                    release.wait(3)
                    return client, sftp
                with patch.object(env, '_connect', connect):
                    task = asyncio.create_task(env.start())
                    while not entered.is_set():
                        await asyncio.sleep(.01)
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                    release.set()
                    for _ in range(100):
                        if client.close.called:
                            break
                        await asyncio.sleep(.01)
                client.close.assert_called_once()
                sftp.close.assert_called_once()
            await env.close()


class SshConfigurationTests(unittest.TestCase):
    def test_validation_rejects_credentials_inline_bad_ports_and_paths_even_disabled(self):
        catalog = builtin_catalog()
        for values in ({'username': 'fixture'}, {'password': 'fixture'}, {'username_env': 'bad name'},
                       {'port': 0}, {'port': 65536}, {'port': True}, {'cwd': 'relative'},
                       {'host': 'user@host'}, {'host': 'host:22/path'}, {'host': 'host:22'},
                       {'operation_timeout_seconds': float('nan')}, {'known_hosts': ''}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                catalog.resolve((MechanismSelection('ssh-env', False, values),))
        for conflict in ('local-env', 'ipython-tool', 'memory-files'):
            with self.subTest(conflict=conflict), self.assertRaises(ValueError):
                catalog.resolve((MechanismSelection('ssh-env'), MechanismSelection(conflict)))

class SshFailureDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_optional_dependency_is_actionable(self):
        env = SshEnv(SshConfig(host='server.example'), username='fixture', password='fixture')
        with patch.dict(sys.modules, paramiko=None):
            with self.assertRaisesRegex(RuntimeError, r'fruitfly-agent\[ssh\]'):
                await env.start()
        await env.close()

    async def test_sftp_handshake_deadline_closes_transport(self):
        env = SshEnv(SshConfig(host='server.example', operation_timeout_seconds=.1), username='fixture', password='fixture')
        closed = threading.Event()
        client = Mock()
        client.close.side_effect = closed.set
        def stall():
            closed.wait(2)
            raise OSError('fixture-private-password')
        client.open_sftp.side_effect = stall
        fake = SimpleNamespace(SSHClient=lambda: client, RejectPolicy=Mock())
        with patch.dict(sys.modules, paramiko=fake):
            with self.assertRaisesRegex(RuntimeError, 'SSH connection failed'):
                await asyncio.wait_for(env.start(), 1)
        self.assertTrue(closed.is_set())
        await env.close()

    async def test_exec_handshake_deadline_closes_channel_without_hanging(self):
        env = SshEnv(SshConfig(host='server.example', operation_timeout_seconds=.1), username='fixture', password='fixture')
        env._sftp = Mock()
        channel, closed = Mock(), threading.Event()
        channel.close.side_effect = closed.set
        def stall(command):
            closed.wait(2)
            raise OSError('fixture-private-password')
        channel.exec_command.side_effect = stall
        transport = Mock()
        transport.open_session.return_value = channel
        env._client = Mock(get_transport=lambda: transport)
        result = await asyncio.wait_for(env.exec('echo x'), 1)
        self.assertFalse(result.is_ok)
        self.assertTrue(closed.is_set())
        self.assertNotIn('fixture-private', result.error)
        await env.close()

    async def test_close_releases_client_and_credentials_even_when_sftp_close_fails(self):
        env = SshEnv(SshConfig(host='server.example'), username='fixture', password='fixture-private-password')
        env._sftp = Mock()
        env._sftp.close.side_effect = OSError('fixture-private-password')
        client = env._client = Mock()
        with self.assertRaises(RuntimeError) as raised:
            await env.close()
        self.assertNotIn('fixture-private', str(raised.exception))
        self.assertEqual('', env._password)
        client.close.assert_called_once()
        await env.close()
