"""Execution identity and ownership contracts, independent of model vendors."""
from __future__ import annotations

import asyncio
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

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ExecutionIdentity):
            raise ValueError('child request requires an execution identity')
        if not isinstance(self.task, str) or not self.task.strip() or len(self.task) > 16000:
            raise ValueError('child task must be nonempty text')
        if not isinstance(self.context, str) or len(self.context) > 16000:
            raise ValueError('child context must be text')


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
