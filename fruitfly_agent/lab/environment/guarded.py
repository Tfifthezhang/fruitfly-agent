"""Environment wrapper enforcing file scopes and local-execution grants."""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import tempfile

from fruitfly_agent.core.errors import Result
from fruitfly_agent.core.env import ExecOptions, ExecutionEnv
from .permissions import PermissionAuthorizer

class GuardedEnv:
    def __init__(self, backend: ExecutionEnv, authorizer: PermissionAuthorizer, *, process_environment: dict[str, str] | None = None) -> None:
        self.backend = backend
        self.authorizer = authorizer
        self.cwd = str(authorizer.policy.workspace)
        self.process_environment = dict(process_environment or {})

    def _call(self, method, path, operation, *args):
        try:
            # Inspect lexical and resolved targets; a protected alias stays protected.
            lexical = Path(path)
            if self.authorizer.forbidden(lexical, operation):
                raise PermissionError('protected credential or host-controlled file')
            target = self.authorizer.check(path, operation)
            return getattr(self.backend, method)(str(target), *args)
        except (OSError, ValueError, PermissionError) as exc:
            return Result.failure(f'Permission denied: {exc}')

    def absolute_path(self, path):
        return Result.success(str(self.authorizer.resolve(path)))

    def join_path(self, parts):
        return Result.success(str(Path(*parts)))

    def canonical_path(self, path):
        return self._call('canonical_path', path, 'read')

    def read_text_file(self, path):
        return self._call('read_text_file', path, 'read')

    def read_binary_file(self, path):
        return self._call('read_binary_file', path, 'read')

    def write_file(self, path, content):
        return self._call('write_file', path, 'write', content)

    def append_file(self, path, content):
        return self._call('append_file', path, 'write', content)

    def file_info(self, path):
        return self._call('file_info', path, 'read')

    def exists(self, path):
        return self._call('exists', path, 'read')

    def list_dir(self, path):
        result = self._call('list_dir', path, 'read')
        if result.is_ok:
            return Result.success([entry for entry in result.unwrap()
                                   if not self.authorizer.forbidden(self.authorizer.resolve(entry.path), 'read')])
        return result

    def create_dir(self, path, recursive=True):
        return self._call('create_dir', path, 'write', recursive)

    def remove(self, path, recursive=False):
        return self._call('remove', path, 'delete', recursive)

    def rename_file(self, source, destination):
        try:
            src = self.authorizer.check(source, 'move')
            dst = self.authorizer.check(destination, 'move')
            return self.backend.rename_file(str(src), str(dst))
        except (OSError, ValueError, PermissionError) as exc:
            return Result.failure(f'Permission denied: {exc}')

    def _temp(self, prefix, suffix=None):
        try:
            if Path(prefix).name != prefix or suffix is not None and Path('x' + suffix).name != 'x' + suffix:
                raise PermissionError('temporary name must not contain paths')
            root = self.authorizer.check(str(Path(self.cwd) / '.fruitfly' / 'tmp'), 'write')
            root.mkdir(parents=True, exist_ok=True)
            if suffix is None:
                return Result.success(tempfile.mkdtemp(prefix=prefix, dir=root))
            fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=root)
            os.close(fd)
            return Result.success(path)
        except (OSError, ValueError, PermissionError) as exc:
            return Result.failure(f'Permission denied: {exc}')

    def create_temp_dir(self, prefix='tmp-'):
        return self._temp(prefix)

    def create_temp_file(self, prefix='', suffix=''):
        return self._temp(prefix, suffix)

    async def exec(self, command, options=None):
        opts = options or ExecOptions()
        try:
            self.authorizer.require_execution(command, opts.cwd or self.cwd)
        except PermissionError as exc:
            return Result.failure(f'Permission denied: {exc}')
        # Explicit options are host-supplied, never inherit the ambient environment.
        env = {**self.process_environment, **(opts.env or {})}
        return await self.backend.exec(command, replace(opts, inherit_env=False, env=env))

__all__ = ['GuardedEnv']
