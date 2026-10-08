"""Serialized confirmation and transient grants owned by one runtime handle."""
from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Awaitable, Callable

from fruitfly_agent.core.tool_runtime.authorization import AuthorizationPrompt
from .events import FrontendEvent, AuthorizationRequested, AuthorizationResolved

class AuthorizationService:
    def __init__(self, *, timeout_seconds: float = 300) -> None:
        if isinstance(timeout_seconds, bool) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError('authorization timeout must be finite and positive')
        self.timeout_seconds = timeout_seconds
        self.available = False
        self.handler: Callable[[AuthorizationPrompt], Awaitable[str]] | None = None
        self.emit: Callable[[FrontendEvent], Awaitable[None]] | None = None
        self._closed = False
        self.pending: AuthorizationPrompt | None = None
        self._answer: asyncio.Future[str] | None = None
        self._lock = asyncio.Lock()
        self._grants: list[tuple[str, tuple[Path, ...]]] = []

    def respond(self, request_id: str, choice: str) -> bool:
        if choice not in {'once', 'session', 'deny'}:
            raise ValueError('unknown authorization choice')
        if self.pending is None or self.pending.request_id != request_id or self._answer is None or self._answer.done():
            return False
        self._answer.set_result(choice)
        self.pending = None
        return True

    def clear(self) -> None:
        self._grants.clear()
        if self._answer is not None and not self._answer.done():
            self._answer.set_result('deny')

    async def close(self) -> None:
        self._closed = True
        self.handler = None
        self.available = False
        self.clear()

    def status(self) -> dict[str, int | bool | str]:
        return {'grants': len(self._grants), 'local_execution': any(op == 'execute' for op, _ in self._grants),
                'pending': self.pending.request_id if self.pending else ''}

    async def confirm(self, prompt: AuthorizationPrompt, signal: asyncio.Event | None = None) -> str:
        async with self._lock:
            if self._closed:
                return 'deny'
            if signal is not None and signal.is_set():
                raise asyncio.CancelledError
            targets = tuple(Path(p) for p in prompt.targets)
            for operation, roots in self._grants:
                if (operation == prompt.operation or prompt.operation == 'read' and operation == 'write') and (
                    operation == 'execute' or all(any(p == r or p.is_relative_to(r) for r in roots) for p in targets)):
                    return 'session'
            if not self.available and self.handler is None:
                return 'deny'
            self.pending = prompt
            self._answer = asyncio.get_running_loop().create_future()
            answer = self._answer
            abort = asyncio.create_task(signal.wait()) if signal is not None else None
            handled: asyncio.Future[str] | None = None
            choice = 'deny'
            try:
                if self.emit is not None:
                    await self.emit(AuthorizationRequested(run_id='', request_id=prompt.request_id,
                        tool_name=prompt.tool_name, operation=prompt.operation, targets=prompt.targets,
                        summary=prompt.summary, session_label=prompt.session_label))
                if self.handler is not None:
                    handled = asyncio.ensure_future(self.handler(prompt))
                watched: set[asyncio.Future] = {answer}
                if abort is not None:
                    watched.add(abort)
                if handled is not None:
                    watched.add(handled)
                done, _ = await asyncio.wait(watched, timeout=self.timeout_seconds, return_when=asyncio.FIRST_COMPLETED)
                if abort is not None and abort in done:
                    raise asyncio.CancelledError
                if answer in done:
                    choice = answer.result()
                elif handled is not None and handled in done:
                    choice = handled.result()
                if choice not in {'once', 'session', 'deny'}:
                    choice = 'deny'
                if choice == 'session':
                    roots = tuple(Path(p) for p in prompt.session_targets) if prompt.session_targets else tuple(dict.fromkeys(p.parent for p in targets))
                    self._grants.append((prompt.operation, roots))
                return choice
            finally:
                self.pending = None
                self._answer = None
                answer.cancel()
                for task in (abort, handled):
                    if task is not None:
                        task.cancel()
                await asyncio.gather(*(t for t in (abort, handled) if t is not None), return_exceptions=True)
                if self.emit is not None:
                    await self.emit(AuthorizationResolved(run_id='', request_id=prompt.request_id,
                                                         operation=prompt.operation, choice=choice))

__all__ = ['AuthorizationService']
