"""Explicit Linux Docker check with a local listener and no model credentials."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

from fruitfly_eval.harbor.access_files import ContainerModelAccess


class DockerModelAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_delivery_under_effective_container_identity(self):
        image = os.environ['FRUITFLY_ACCESS_TEST_IMAGE']
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix='ff-access-') as temporary:
            work = Path(temporary)
            socket_path = work / 'relay.sock'
            async def close(_reader, writer):
                writer.close()
                await writer.wait_closed()
            server = await asyncio.start_unix_server(close, path=socket_path)
            socket_path.chmod(0o600)
            try:
                for default_uid, explicit_uid in ((0, None), (1000, None), (0, 1000)):
                    with self.subTest(default_uid=default_uid, explicit_uid=explicit_uid):
                        def docker(*args):
                            return subprocess.run(['docker', *args], check=True, text=True,
                                                  capture_output=True, timeout=25).stdout.strip()
                        container = docker('run', '--pull=never', '-d', '--network=none', '--user',
                                           str(default_uid), '-v', f'{root}:/source:ro',
                                           '-v', f'{work}:/relay:ro', '-e', 'PYTHONPATH=/source',
                                           '--entrypoint', 'sleep', image, '120')
                        try:
                            docker('exec', '-u', '0', container, 'mkdir', '-p',
                                   '/installed-agent/fruitfly/runtime')
                            async def execute(_environment, *, command, env, timeout_sec, uid=explicit_uid):
                                user = () if uid is None else ('-u', str(uid))
                                return SimpleNamespace(stdout=await asyncio.to_thread(
                                    docker, 'exec', *user, container, 'sh', '-c', command))
                            async def execute_root(*args, **kwargs):
                                return await execute(*args, **kwargs, uid=0)
                            async def upload(source, target):
                                await asyncio.to_thread(docker, 'cp', str(source), f'{container}:{target}')
                                # Force a mismatched owner even where Docker normalizes uploads.
                                await asyncio.to_thread(docker, 'exec', '-u', '0', container,
                                                        'chown', '1019:1020', target)
                            async def stop(*, delete):
                                await asyncio.to_thread(docker, 'stop', container)
                            env = SimpleNamespace(upload_file=upload, stop=stop)
                            agent = SimpleNamespace(runtime_python='python', runtime_environment={},
                                                    exec_as_agent=execute, exec_as_root=execute_root)
                            desc = {'models': {'fixture': {
                                'spec': {'sdk': 'openai', 'protocol': 'chat-completions',
                                         'service': 'opencode-go', 'model': 'fixture',
                                         'context_window': 8192,
                                         'access': {'integration': 'opencode-go', 'account': 'fixture'}},
                                'authorization': {'integration': 'opencode-go', 'account': 'fixture',
                                                  'identity': 'fixture', 'label': 'fixture'},
                                'socket': '/relay/relay.sock', 'grant': 'fixture-only',
                                'network_url': None, 'ca': None,
                            }}}
                            async with ContainerModelAccess(agent, env) as files:
                                self.assertEqual(files.identity[0],
                                                 default_uid if explicit_uid is None else explicit_uid)
                                if files.identity[0] == 0:
                                    await files.publish(desc, ca_source=None)
                                else:
                                    with self.assertRaises(subprocess.CalledProcessError):
                                        await files.publish(desc, ca_source=None)
                                    # Confirm delivery succeeded and the transport check rejected access.
                                    actual_uid = docker('exec', '-u', '0', container, 'stat', '-c', '%u',
                                                        str(files.descriptor_path))
                                    self.assertEqual(actual_uid, '1000')
                            docker('exec', '-u', '0', container, 'test', '!', '-e', str(files.directory))
                            if files.identity[0] == 0:
                                published = asyncio.Event()
                                cancelled_files = ContainerModelAccess(agent, env)
                                async def cancelled_run():
                                    async with cancelled_files:
                                        await cancelled_files.publish(desc, ca_source=None)
                                        published.set()
                                        await asyncio.Future()
                                trial = asyncio.create_task(cancelled_run())
                                try:
                                    await asyncio.wait_for(published.wait(), 25)
                                finally:
                                    trial.cancel()
                                    with self.assertRaises(asyncio.CancelledError):
                                        await trial
                                docker('exec', '-u', '0', container, 'test', '!', '-e',
                                       str(cancelled_files.directory))
                            if default_uid == 1000:
                                ca = work / 'ca.pem'
                                key = work / 'key.pem'
                                subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048',
                                                '-nodes', '-days', '1', '-subj', '/CN=localhost',
                                                '-addext', 'subjectAltName=DNS:localhost',
                                                '-keyout', str(key), '-out', str(ca)], check=True,
                                               capture_output=True, timeout=15)
                                docker('cp', str(ca), f'{container}:/tmp/fixture-ca.pem')
                                docker('cp', str(key), f'{container}:/tmp/fixture-key.pem')
                                listener = (
                                    "import socket, ssl; "
                                    "ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); "
                                    "ctx.load_cert_chain('/tmp/fixture-ca.pem', '/tmp/fixture-key.pem'); "
                                    "sock = socket.create_server(('127.0.0.1', 0)); "
                                    "open('/tmp/fixture-port', 'w').write(str(sock.getsockname()[1])); "
                                    "ctx.wrap_socket(sock.accept()[0], server_side=True).close()"
                                )
                                docker('exec', '-d', '-u', '0', container, 'python', '-c', listener)
                                port = docker('exec', container, 'sh', '-c',
                                              'for i in 1 2 3 4 5; do test -s /tmp/fixture-port '
                                              '&& exec cat /tmp/fixture-port; sleep 1; done; exit 1')
                                desc['models']['fixture']['network_url'] = f'https://localhost:{port}'
                                async with ContainerModelAccess(agent, env) as tls_files:
                                    await tls_files.publish(desc, ca_source=ca)
                                docker('exec', '-u', '0', container, 'test', '!', '-e',
                                       str(tls_files.directory))
                        finally:
                            docker('rm', '-f', container)
            finally:
                server.close()
                await server.wait_closed()
