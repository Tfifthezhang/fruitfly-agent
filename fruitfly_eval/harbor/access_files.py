"""Deliver and retire private model access files in one Harbor execution."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import ssl
import stat
import sys
import tempfile
from typing import Any, Awaitable
from urllib.parse import urlsplit
from uuid import uuid4


ROOT = Path('/installed-agent/fruitfly/runtime/model-access')
TIMEOUT = 10


class ContainerModelAccess:
    def __init__(self, agent: Any, environment: Any) -> None:
        self.agent = agent
        self.environment = environment
        self.execution_id = uuid4().hex
        self.directory = ROOT / self.execution_id
        self.descriptor_path = self.directory / 'model-access.json'
        self.identity: list[int] = []
        self.started = False
        self.pending: asyncio.Future[Any] | None = None

    async def _exec(self, operation: str, *args: str, root: bool = False) -> Any:
        execute = self.agent.exec_as_root if root else self.agent.exec_as_agent
        return await execute(self.environment, command=shlex.join([
            self.agent.runtime_python, '-P', '-m', 'fruitfly_eval.harbor.access_files',
            operation, self.execution_id, *args,
        ]), env=self.agent.runtime_environment, timeout_sec=TIMEOUT)

    async def __aenter__(self) -> ContainerModelAccess:
        try:
            result = await self._exec('identity')
            identity = json.loads(result.stdout)
        except Exception as exc:
            raise RuntimeError('Could not resolve model access execution identity') from exc
        if (not isinstance(identity, list) or len(identity) != 2
                or any(type(value) is not int or value < 0 for value in identity)):
            raise ValueError('Invalid model access execution identity')
        self.identity = identity
        return self

    async def publish(self, descriptor: dict[str, Any], *, ca_source: Path | None) -> None:
        self.started = True
        await self._finish(self._exec('create', root=True))
        material = deepcopy(descriptor)
        with tempfile.TemporaryDirectory(prefix='fruitfly-model-access-') as directory:
            source = Path(directory) / 'access.json'
            if ca_source is not None:
                ca_path = self.directory / 'relay-ca.pem'
                await self._upload(ca_source, ca_path)
                for entry in material['models'].values():
                    entry['ca'] = str(ca_path)
            with os.fdopen(os.open(source, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
                           'w', encoding='utf-8') as stream:
                json.dump(material, stream)
            await self._upload(source, self.descriptor_path)
        await self._finish(self._exec('publish', *(str(value) for value in self.identity),
                                     *(['tls'] if ca_source is not None else []), root=True))
        await self._exec('probe', *(str(value) for value in self.identity))

    async def _upload(self, source: Path, target: Path) -> None:
        await self._finish(self.environment.upload_file(source, str(target)))

    async def _finish(self, operation: Awaitable[Any]) -> None:
        # Drain a cancelled write before attempting to remove its target.
        task = asyncio.ensure_future(operation)
        self.pending = task
        try:
            await asyncio.wait_for(asyncio.shield(task), TIMEOUT)
        except (asyncio.CancelledError, TimeoutError):
            try:
                await asyncio.wait_for(asyncio.shield(task), TIMEOUT)
            except Exception:
                pass
            raise
        finally:
            if task.done():
                self.pending = None

    async def _retire(self) -> None:
        if self.pending is not None:
            self.pending.cancel()
            raise RuntimeError('Model access write retirement unconfirmed')
        await self._exec('remove', root=True)

    async def __aexit__(self, kind: Any, primary: BaseException | None, trace: Any) -> None:
        if not self.started:
            return
        cleanup = asyncio.create_task(self._retire())
        cancellation = None
        try:
            try:
                await asyncio.wait_for(asyncio.shield(cleanup), TIMEOUT + 2)
            except asyncio.CancelledError as exc:
                cancellation = exc
                await asyncio.wait_for(asyncio.shield(cleanup), TIMEOUT + 2)
        except BaseException as error:
            cleanup.cancel()
            failure = RuntimeError('Model access file cleanup failed')
            failure.add_note('Cleanup failure type: ' + type(error).__name__)
            try:
                await asyncio.wait_for(self.environment.stop(delete=False), TIMEOUT)
            except BaseException as stop_error:
                failure.add_note('Environment stop unconfirmed: ' + type(stop_error).__name__)
            else:
                failure.add_note('Environment stopped')
            raise failure from (primary or cancellation or error)
        if cancellation is not None:
            raise cancellation


def _trusted_directory(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError('Unsafe model access parent directory')


def _probe(path: Path) -> None:
    from fruitfly_agent.providers.auth.stores import read_private_json
    from fruitfly_agent.providers.gateway.access import access_registry

    access_registry(path)
    seen = set()
    for entry in read_private_json(path)['models'].values():
        endpoint = entry['network_url'] or entry['socket']
        if endpoint in seen:
            continue
        seen.add(endpoint)
        if entry['network_url']:
            url = urlsplit(endpoint)
            hostname = url.hostname
            if url.scheme != 'https' or hostname is None:
                raise ValueError('Invalid model relay TLS endpoint')
            tls = ssl.create_default_context(cafile=entry['ca'])
            with socket.create_connection((hostname, url.port or 443), timeout=3) as connection:
                with tls.wrap_socket(connection, server_hostname=hostname):
                    pass
        else:
            with socket.socket(socket.AF_UNIX) as connection:
                connection.settimeout(3)
                connection.connect(endpoint)


def _operate(operation: str, execution_id: str, *args: str) -> None:
    if re.fullmatch(r'[0-9a-f]{32}', execution_id) is None:
        raise ValueError('Invalid model access execution ID')
    directory = ROOT / execution_id
    if operation == 'identity':
        print(json.dumps([os.getuid(), os.getgid()]))
        return
    if operation == 'probe':
        if [os.getuid(), os.getgid()] != list(map(int, args)):
            raise ValueError('Model access execution identity changed')
        _probe(directory / 'model-access.json')
        return

    for parent in reversed(ROOT.parents):
        _trusted_directory(parent)
    if operation == 'create':
        try:
            ROOT.mkdir(mode=0o755)
        except FileExistsError:
            pass
        _trusted_directory(ROOT)
        ROOT.chmod(0o755)
    elif operation == 'remove' and not ROOT.exists() and not ROOT.is_symlink():
        return
    _trusted_directory(ROOT)
    if operation == 'create':
        directory.mkdir(mode=0o700)
    elif operation == 'publish':
        _trusted_directory(directory)
        uid, gid = map(int, args[:2])
        names = ['model-access.json']
        if args[2:] == ('tls',):
            names.append('relay-ca.pem')
        for name in names:
            fd = os.open(directory / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError('Invalid uploaded model access file')
                os.fchmod(fd, 0o600)
                os.fchown(fd, uid, gid)
            finally:
                os.close(fd)
        os.chmod(directory, 0o700)
        os.chown(directory, uid, gid)
    elif operation == 'remove':
        try:
            shutil.rmtree(directory)
        except FileNotFoundError:
            pass
    else:
        raise ValueError('Unknown model access operation')


if __name__ == '__main__':
    try:
        _operate(*sys.argv[1:])
    except Exception as exc:
        operation = sys.argv[1] if len(sys.argv) > 1 else 'operation'
        reason = type(exc).__name__
        if isinstance(exc, OSError) and type(exc.errno) is int:
            reason += f' (errno {exc.errno})'
        print(f'Model access {operation} failed as {os.getuid()}:{os.getgid()}: {reason}',
              file=sys.stderr)
        sys.exit(1)
