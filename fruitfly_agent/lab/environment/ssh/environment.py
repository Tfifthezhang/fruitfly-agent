"""Password-authenticated SSH environment with SFTP file operations."""
from __future__ import annotations

import asyncio
import codecs
import errno
import json
import logging
import math
from pathlib import Path
import posixpath
import re
import shlex
import stat
import threading
import time
import uuid

from fruitfly_agent.core.env import ExecOptions, ExecResult, FileInfo
from fruitfly_agent.core.errors import Result
from .config import SshConfig
from .supervisor import PROGRAM


class SshEnv:
    def __init__(self, config: SshConfig, *, username: str, password: str):
        if not config.host:
            raise ValueError('SSH host is required before enabling the remote environment')
        if not username or not password:
            raise ValueError('SSH username and password must be set in the host secret environment')
        self.config = config
        self.cwd = config.cwd
        self._username, self._password = username, password
        self._client = self._sftp = None
        self._closed = False
        self._channels: set = set()

    def _connect(self):
        try:
            import paramiko
        except ImportError:
            raise ModuleNotFoundError("SSH requires the optional dependency: pip install 'fruitfly-agent[ssh]'") from None
        client = paramiko.SSHClient()
        # Paramiko's diagnostic messages can contain account names. Keep this
        # transport off application/root logging, including DEBUG configurations.
        logger = logging.getLogger('fruitfly.ssh.private')
        logger.propagate = False
        logger.setLevel(logging.CRITICAL)
        if not logger.handlers:
            logger.addHandler(logging.NullHandler())
        client.set_log_channel(logger.name)
        try:
            client.load_host_keys(str(Path(self.config.known_hosts).expanduser()))
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            deadline = self.config.connect_timeout_seconds
            client.connect(self.config.host, port=self.config.port, username=self._username,
                           password=self._password, allow_agent=False, look_for_keys=False,
                           timeout=deadline, banner_timeout=deadline, auth_timeout=deadline,
                           channel_timeout=deadline)
            client.get_transport().set_keepalive(15)
            # Paramiko's subsystem negotiation does not honor channel read
            # timeouts. Closing the transport also bounds that handshake.
            watchdog = threading.Timer(self.config.operation_timeout_seconds, self._quiet_close, (client,))
            watchdog.daemon = True
            watchdog.start()
            try:
                sftp = client.open_sftp()
                sftp.get_channel().settimeout(self.config.operation_timeout_seconds)
                if not stat.S_ISDIR(sftp.stat(self.cwd).st_mode):
                    raise ValueError('remote workspace is not a directory')
            finally:
                watchdog.cancel()
            return client, sftp
        except BaseException:
            client.close()
            raise

    async def start(self):
        if self._closed:
            raise RuntimeError('SSH environment is closed')
        if self._client is not None:
            return
        task = asyncio.create_task(asyncio.to_thread(self._connect))
        try:
            self._client, self._sftp = await asyncio.shield(task)
            if self._closed:
                await self.close()
                raise RuntimeError('SSH environment closed during startup')
        except asyncio.CancelledError:
            # A worker cannot be interrupted. Close its eventual result even
            # when Application has already retired the candidate runtime.
            def discard(future):
                if not future.cancelled() and future.exception() is None:
                    client, sftp = future.result()
                    self._quiet_close(sftp)
                    self._quiet_close(client)
            task.add_done_callback(discard)
            raise
        except ModuleNotFoundError:
            raise RuntimeError("SSH requires the optional dependency: pip install 'fruitfly-agent[ssh]'") from None
        except Exception:
            raise RuntimeError('SSH connection failed; check host key, address, port, credentials and remote directory') from None

    async def close(self):
        self._closed = True
        failed = False
        for channel in tuple(self._channels):
            self._cancel(channel)
            try:
                channel.close()
            except Exception:
                failed = True
        self._channels.clear()
        if self._sftp is not None:
            try:
                self._sftp.close()
            except Exception:
                failed = True
            finally:
                self._sftp = None
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                failed = True
            finally:
                self._client = None
        self._username = self._password = ''
        if failed:
            raise RuntimeError('SSH resource cleanup failed; connection or remote cleanup may be incomplete') from None

    def _ready(self):
        if self._closed or self._sftp is None:
            raise OSError('SSH environment is not connected')
        return self._sftp

    def _result(self, operation, function):
        try:
            return Result.success(function())
        except Exception:
            # Never serialize transport exceptions: third-party messages can
            # include authentication values, paths or remote server banners.
            return Result.failure(f'SSH {operation} failed; check connection and remote permissions')

    def _path(self, path):
        if not isinstance(path, str) or '\x00' in path:
            raise ValueError('invalid remote path')
        return path if path.startswith('/') else posixpath.join(self.cwd, path)

    def absolute_path(self, path):
        return self._result('absolute_path', lambda: self._path(path))

    def join_path(self, parts):
        return self._result('join_path', lambda: posixpath.join(*parts))

    def _canonical(self, path):
        sftp = self._ready()
        pending = self._path(path).split('/')
        resolved: list[str] = []
        links = 0
        while pending:
            part = pending.pop(0)
            if part in ('', '.'):
                continue
            if part == '..':
                if resolved:
                    resolved.pop()
                continue
            candidate = '/' + '/'.join([*resolved, part])
            try:
                info = sftp.lstat(candidate)
            except OSError as exc:
                if exc.errno != errno.ENOENT:
                    raise
                resolved.append(part)
                continue
            if stat.S_ISLNK(info.st_mode):
                links += 1
                if links > 40:
                    raise OSError('too many symbolic links')
                target = sftp.readlink(candidate)
                if target.startswith('/'):
                    resolved = []
                pending = target.split('/') + pending
            else:
                resolved.append(part)
        return '/' + '/'.join(resolved)

    def canonical_path(self, path):
        return self._result('canonical_path', lambda: self._canonical(path))

    def read_binary_file(self, path):
        def read():
            with self._ready().open(self._path(path), 'rb') as file:
                return file.read()
        return self._result('read', read)

    def read_text_file(self, path):
        data = self.read_binary_file(path)
        return Result.success(data.unwrap().decode('utf-8', errors='replace')) if data.is_ok else data

    def _mkdir(self, path, recursive=True):
        sftp = self._ready()
        try:
            info = sftp.stat(path)
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                raise
            parent = posixpath.dirname(path)
            if recursive and parent and parent != path:
                self._mkdir(parent)
            sftp.mkdir(path)
        else:
            if not stat.S_ISDIR(info.st_mode):
                raise OSError('not a directory')

    def create_dir(self, path, recursive=True):
        return self._result('mkdir', lambda: self._mkdir(self._path(path), recursive))

    def _write(self, path, content, mode):
        target = self._path(path)
        self._mkdir(posixpath.dirname(target))
        with self._ready().open(target, mode) as file:
            file.write(content.encode('utf-8') if isinstance(content, str) else content)

    def write_file(self, path, content):
        return self._result('write', lambda: self._write(path, content, 'wb'))

    def append_file(self, path, content):
        return self._result('append', lambda: self._write(path, content, 'ab'))

    def rename_file(self, source, destination):
        return self._result('rename', lambda: self._ready().posix_rename(self._path(source), self._path(destination)))

    def _info(self, path, info=None):
        target = self._path(path)
        info = info or self._ready().lstat(target)
        kind = 'symlink' if stat.S_ISLNK(info.st_mode) else 'directory' if stat.S_ISDIR(info.st_mode) else 'file'
        return FileInfo(posixpath.basename(target), target, kind, info.st_size or 0, (info.st_mtime or 0) * 1000)

    def file_info(self, path):
        return self._result('stat', lambda: self._info(path))

    def list_dir(self, path):
        def listing():
            target = self._path(path)
            return [self._info(posixpath.join(target, item.filename), item)
                    for item in sorted(self._ready().listdir_attr(target), key=lambda item: item.filename)]
        return self._result('list', listing)

    def exists(self, path):
        def check():
            try:
                self._ready().stat(self._path(path))
                return True
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    return False
                raise
        return self._result('exists', check)

    def _remove(self, path, recursive):
        sftp = self._ready()
        try:
            info = sftp.lstat(path)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                return
            raise
        if stat.S_ISDIR(info.st_mode):
            if recursive:
                for entry in sftp.listdir_attr(path):
                    self._remove(posixpath.join(path, entry.filename), True)
            sftp.rmdir(path)
        else:
            sftp.remove(path)

    def remove(self, path, recursive=False):
        return self._result('remove', lambda: self._remove(self._path(path), recursive))

    def _temp(self, prefix, suffix=None):
        if any('/' in value or '\x00' in value for value in (prefix, suffix or '')):
            raise ValueError('temporary name must not contain paths')
        root = posixpath.join(self.cwd, '.fruitfly', 'tmp')
        self._mkdir(root)
        path = posixpath.join(root, prefix + uuid.uuid4().hex + (suffix or ''))
        if suffix is None:
            self._ready().mkdir(path, mode=0o700)
        else:
            with self._ready().open(path, 'wx'):
                pass
            self._ready().chmod(path, 0o600)
        return path

    def create_temp_dir(self, prefix='tmp-'):
        return self._result('temporary directory', lambda: self._temp(prefix))

    def create_temp_file(self, prefix='', suffix=''):
        return self._result('temporary file', lambda: self._temp(prefix, suffix))

    def with_permissions(self, policy, *, confirm, audit=None):
        from .permissions import RemoteAuthorizer, GuardedSshEnv
        authorizer = RemoteAuthorizer(self, policy, confirm=confirm, audit=audit)
        return GuardedSshEnv(self, authorizer), authorizer

    @staticmethod
    def _quiet_close(resource):
        try:
            resource.close()
        except Exception:
            pass

    @staticmethod
    def _cancel(channel):
        try:
            channel.settimeout(.1)
            channel.sendall(b'cancel\n')
            channel.shutdown_write()
        except Exception:
            pass

    async def exec(self, command, options=None):
        opts = options or ExecOptions()
        channel = None
        try:
            self._ready()
            env = opts.env or {}
            if opts.timeout_seconds is not None and (isinstance(opts.timeout_seconds, bool) or
                    not isinstance(opts.timeout_seconds, (int, float)) or
                    not math.isfinite(opts.timeout_seconds) or opts.timeout_seconds <= 0):
                raise ValueError('invalid execution deadline')
            if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) or not isinstance(value, str) or '\x00' in value for key, value in env.items()):
                raise ValueError('invalid execution environment')
            payload = json.dumps({'command': command, 'cwd': self._path(opts.cwd or self.cwd),
                                  'env': env, 'inherit_env': opts.inherit_env, 'timeout': opts.timeout_seconds})
            transport = self._client.get_transport()
            # Opening/starting channels is blocking. Cancellation during this
            # bounded handshake must still close its eventual result.
            def open_channel():
                result = transport.open_session(timeout=self.config.operation_timeout_seconds)
                watchdog = threading.Timer(self.config.operation_timeout_seconds, self._quiet_close, (result,))
                watchdog.daemon = True
                watchdog.start()
                try:
                    result.settimeout(self.config.operation_timeout_seconds)
                    result.exec_command('python3 -u -c ' + shlex.quote(PROGRAM) + ' ' + shlex.quote(payload))
                    return result
                except BaseException:
                    self._quiet_close(result)
                    raise
                finally:
                    watchdog.cancel()
            started = time.monotonic()
            opening = asyncio.create_task(asyncio.to_thread(open_channel))
            try:
                channel = await asyncio.shield(opening)
            except asyncio.CancelledError:
                def discard(future):
                    if not future.cancelled() and future.exception() is None:
                        abandoned = future.result()
                        self._cancel(abandoned)
                        self._quiet_close(abandoned)
                opening.add_done_callback(discard)
                raise
            if self._closed:
                raise OSError('SSH environment closed during command startup')
            self._channels.add(channel)
            channel.settimeout(.1)
            cancelled = False
            cleanup_deadline = None
            output, errors = [], []
            decoders = [codecs.getincrementaldecoder('utf-8')(errors='replace') for _ in range(2)]
            while True:
                for index, (ready, receive, parts, callback) in enumerate((
                    (channel.recv_ready, channel.recv, output, opts.on_stdout),
                    (channel.recv_stderr_ready, channel.recv_stderr, errors, opts.on_stderr),
                )):
                    # Drain a bounded chunk from each stream per iteration.
                    if ready():
                        chunk = decoders[index].decode(receive(65536))
                        parts.append(chunk)
                        if callback is not None and chunk:
                            try:
                                await callback(chunk)
                            except Exception:
                                pass
                now = time.monotonic()
                if opts.timeout_seconds and now - started >= opts.timeout_seconds and not cancelled:
                    cancelled = True
                    self._cancel(channel)
                    cleanup_deadline = now + 5
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    code = channel.recv_exit_status()
                    if code < 0:
                        raise OSError('SSH disconnected without exit status')
                    output.append(decoders[0].decode(b'', final=True))
                    errors.append(decoders[1].decode(b'', final=True))
                    return Result.success(ExecResult(''.join(output), ''.join(errors), code, cancelled))
                if cleanup_deadline is not None and now >= cleanup_deadline:
                    raise OSError('remote cancellation could not be confirmed')
                if not transport.is_active():
                    raise OSError('SSH transport disconnected')
                await asyncio.sleep(.01)
        except asyncio.CancelledError:
            if channel is not None:
                self._cancel(channel)
                # Give the supervisor a bounded opportunity to reap its group.
                end = time.monotonic() + 2
                while not channel.exit_status_ready() and time.monotonic() < end:
                    if channel.recv_ready():
                        channel.recv(65536)
                    if channel.recv_stderr_ready():
                        channel.recv_stderr(65536)
                    await asyncio.sleep(.01)
            raise
        except Exception:
            if channel is not None:
                self._cancel(channel)
            return Result.failure('SSH execution failed; connection or remote cleanup may be incomplete')
        finally:
            if channel is not None:
                self._channels.discard(channel)
                self._quiet_close(channel)
