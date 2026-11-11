"""Execution identity and ownership contracts, independent of model vendors."""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Literal, Protocol

from fruitfly_agent.core.data_model import AgentLoopResult
from fruitfly_agent.lab.catalog.agent_runtime import PreparedAgentRuntime


ExecutionState = Literal['queued', 'running', 'cancelling', 'completed', 'failed',
                         'cancelled', 'timed_out', 'interrupted']
CleanupState = Literal['pending', 'confirmed', 'failed']


@dataclass(frozen=True)
class ExecutionIdentity:
    scope_id: str
    agent_id: str
    run_id: str

    def __post_init__(self) -> None:
        for value in (self.scope_id, self.agent_id, self.run_id):
            if (not isinstance(value, str) or not value or len(value) > 128
                    or not all(c.isascii() and (c.isalnum() or c in '-_') for c in value)):
                raise ValueError('execution identities must be bounded opaque tokens')


@dataclass(frozen=True)
class ChildRequest:
    identity: ExecutionIdentity
    task: str
    context: str = ''
    worker: str = ''
    materials: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (not isinstance(self.worker, str) or len(self.worker) > 128
                or not isinstance(self.materials, tuple) or len(self.materials) > 256
                or any(not isinstance(v, str) or not v or len(v) > 16000 for v in self.materials)
                or len(set(self.materials)) != len(self.materials)):
            raise ValueError('invalid delegated worker or material identities')
        if not isinstance(self.identity, ExecutionIdentity):
            raise ValueError('child request requires an execution identity')
        if not isinstance(self.task, str) or not self.task.strip() or len(self.task) > 16000:
            raise ValueError('child task must be nonempty text')
        if not isinstance(self.context, str) or len(self.context) > 16000:
            raise ValueError('child context must be text')


@dataclass(frozen=True)
class ChildExecutionPolicy:
    timeout_seconds: float
    max_model_requests: int
    instructions: str

    def __post_init__(self):
        if (isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float))
                or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0):
            raise ValueError('child policy deadline must be finite and positive')
        if type(self.max_model_requests) is not int or self.max_model_requests < 1:
            raise ValueError('child policy request count must be a positive integer')
        if not isinstance(self.instructions, str) or len(self.instructions) > 240000:
            raise ValueError('child policy instructions require bounded text')


class ChildExecution(Protocol):
    """One active invocation; the factory owns independent mutable state.

    Close releases only owned resources. Borrowed host resources remain live.
    Cancellation is a request, not evidence that execution or effects stopped.
    """

    async def run(self, request: ChildRequest, *, signal: asyncio.Event) -> AgentLoopResult: ...

    async def close(self) -> None: ...


class ChildExecutionFactory(Protocol):
    """Prepare a child without starting model work; clean partial construction."""

    async def __call__(self, request: ChildRequest) -> PreparedAgentRuntime: ...
