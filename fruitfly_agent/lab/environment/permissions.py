"""Small host-owned file and local-execution policy; this is not a sandbox."""
from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable

from fruitfly_agent.core.tool_runtime.authorization import (
    AuthorizationRequest, AuthorizationDecision, AuthorizationPrompt,
)
from fruitfly_agent.lab.tools.path_utils import normalize_tool_path

Confirmation = Callable[[AuthorizationPrompt, asyncio.Event | None], Awaitable[str]]

@dataclass(frozen=True)
class PermissionPolicy:
    workspace: Path
    read_roots: tuple[Path, ...] = ()
    write_roots: tuple[Path, ...] = ()
    sensitive_paths: tuple[Path, ...] = ()
    readonly_paths: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, 'workspace', self.workspace.resolve())
        for name in ('read_roots', 'write_roots', 'sensitive_paths', 'readonly_paths'):
            object.__setattr__(self, name, tuple(Path(p).resolve() for p in getattr(self, name)))

    def identity(self) -> dict:
        return {'implementation': 'local-permissions-v1', 'workspace': str(self.workspace),
                **{name: [str(p) for p in getattr(self, name)] for name in
                   ('read_roots', 'write_roots', 'sensitive_paths', 'readonly_paths')},
                'outside_workspace': 'confirm', 'local_execution': 'confirm',
                'secret_names': ['.env', '.env.* (except examples)', 'secrets.env'],
                'environment': 'minimal-v1'}

@dataclass
class _Grant:
    entries: tuple[tuple[str, Path], ...]
    execute: bool
    command: str | None
    cwd: Path | None
    active: bool = True

class PermissionAuthorizer:
    def __init__(self, policy: PermissionPolicy, *, confirm: Confirmation | None = None, audit: Callable[[dict], None] | None = None) -> None:
        self.policy = policy
        self.confirm = confirm
        self.audit = audit
        self._grant: ContextVar[_Grant | None] = ContextVar('operation_authorization', default=None)

    def resolve(self, path: str) -> Path:
        value = Path(normalize_tool_path(path))
        return (value if value.is_absolute() else self.policy.workspace / value).resolve()

    def forbidden(self, path: Path, operation: str) -> bool:
        candidates = (path, *path.parents)
        for candidate in candidates:
            name = candidate.name
            if (name in {'.env', 'secrets.env'} or name.startswith('.env.')
                    and name not in {'.env.example', '.env.sample', '.env.template'}):
                return True
        for secret in self.policy.sensitive_paths:
            if path == secret or path.is_relative_to(secret):
                return True
            try:
                if path.exists() and secret.exists() and path.samefile(secret):
                    return True
            except OSError:
                return True
            if operation in {'delete', 'move'} and secret.is_relative_to(path):
                return True
        if operation != 'read':
            for protected in self.policy.readonly_paths:
                if path == protected or path.is_relative_to(protected):
                    return True
                try:
                    if path.exists() and protected.exists() and path.samefile(protected):
                        return True
                except OSError:
                    return True
                if operation in {'delete', 'move'} and protected.is_relative_to(path):
                    return True
        return False

    def check(self, path: str, operation: str) -> Path:
        canonical = self.resolve(path)
        if self.forbidden(Path(normalize_tool_path(path)), operation) or self.forbidden(canonical, operation):
            raise PermissionError('protected credential or host-controlled file')
        if operation in {'read', 'write'}:
            roots = (self.policy.workspace, *self.policy.write_roots,
                     *(self.policy.read_roots if operation == 'read' else ()))
            if any(canonical == root or canonical.is_relative_to(root) for root in roots):
                return canonical
        grant = self._grant.get()
        for allowed_operation, target in grant.entries if grant is not None and grant.active else ():
            if canonical == target and (operation == allowed_operation or operation == 'read' and allowed_operation == 'write'):
                return canonical
        raise PermissionError('operation requires user confirmation')

    def require_execution(self, command: str | None = None, cwd: str | None = None) -> None:
        grant = self._grant.get()
        if grant is None or not grant.active or not grant.execute:
            raise PermissionError('local execution requires user confirmation')
        if command is not None and grant.command != command:
            raise PermissionError('command differs from the authorized call')
        if cwd is not None and grant.cwd != self.resolve(cwd):
            raise PermissionError('working directory differs from the authorized call')

    @asynccontextmanager
    async def authorize(self, request: AuthorizationRequest, *, signal: asyncio.Event | None = None) -> AsyncIterator[AuthorizationDecision]:
        descriptor = request.permission
        operation = descriptor.operation if descriptor else 'unknown'
        paths: tuple[Path, ...] = ()
        allowed = False
        reason = 'undeclared tool operation'
        token = None
        grant = None
        try:
            if signal is not None and signal.is_set():
                raise asyncio.CancelledError
            if descriptor is None or operation not in {'read', 'write', 'delete', 'move', 'execute'}:
                yield AuthorizationDecision(False, reason)
                return
            if operation == 'execute':
                cwd = request.arguments.get('cwd', str(self.policy.workspace))
                paths = (self.resolve(cwd),)
                needs_confirmation = True
            else:
                if not descriptor.path_arguments:
                    reason = 'file operation has no declared targets'
                    yield AuthorizationDecision(False, reason)
                    return
                paths = tuple(self.resolve(request.arguments[key]) for key in descriptor.path_arguments)
                # Retain the lexical names too: a .env symlink must not turn into an ordinary file.
                for key, path in zip(descriptor.path_arguments, paths):
                    lexical = Path(normalize_tool_path(request.arguments[key]))
                    if self.forbidden(lexical, operation) or self.forbidden(path, operation):
                        reason = 'protected credential or host-controlled file'
                        yield AuthorizationDecision(False, reason)
                        return
                needs_confirmation = False
                for path in paths:
                    try:
                        self.check(str(path), operation)
                    except PermissionError:
                        needs_confirmation = True
            reason = 'within configured file scope'
            if needs_confirmation:
                if self.confirm is None:
                    reason = 'user confirmation is unavailable'
                    yield AuthorizationDecision(False, reason)
                    return
                summary = (str(request.arguments.get('command', request.arguments.get('code', 'local code execution')))
                           if operation == 'execute' else 'File operation')
                session_targets = tuple(dict.fromkeys(str(p if p.is_dir() else p.parent) for p in paths))
                session_label = ('Allow local code execution for this session (current user permissions)'
                                 if operation == 'execute' else f'Allow {operation} in these directories for this session: ' +
                                 ', '.join(session_targets))
                prompt = AuthorizationPrompt(uuid.uuid4().hex, request.tool_name, operation,
                                             tuple(str(p) for p in paths), summary, session_label, session_targets)
                choice = await self.confirm(prompt, signal)
                if choice not in {'once', 'session'}:
                    reason = 'user declined or confirmation expired'
                    yield AuthorizationDecision(False, reason)
                    return
                reason = 'user approved ' + choice
            if signal is not None and signal.is_set():
                raise asyncio.CancelledError
            # Exact targets are checked again by the backend at actual access.
            grant = _Grant(tuple((operation, p) for p in paths), operation == 'execute',
                           request.arguments.get('command'), paths[0] if operation == 'execute' else None)
            token = self._grant.set(grant)
            allowed = True
            yield AuthorizationDecision(True, reason)
        finally:
            if grant is not None:
                grant.active = False
            if token is not None:
                self._grant.reset(token)
            if self.audit is not None:
                self.audit({'call_id': request.call_id, 'tool': request.tool_name,
                            'operation': operation, 'allowed': allowed, 'reason': reason})

__all__ = ['PermissionPolicy', 'PermissionAuthorizer']
