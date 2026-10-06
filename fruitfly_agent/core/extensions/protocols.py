"""Structural contracts for injected runtime components.

Implement protocols without runtime registration. Core handles ordinary
component failures at the documented call sites and propagates cancellation;
see ../README.md for runtime rules. The ``Like`` suffix distinguishes a
protocol from its concrete Core implementation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..data_model.context import ContextDecision, ContextSnapshot
from ..data_model.runtime import AgentLoopContext, ProviderView
from ..env.protocols import ExecutionEnv, FileSystem, Shell  # noqa: F401 — re-export seam
from ..model_stream import AssistantMessageEventStream
from ..session.protocol import SessionLike


@runtime_checkable
class Provider(Protocol):
    """Callable model adapter returning an asynchronous response stream.

    Call ``provider(view, signal=signal)`` and consume its events, then await
    ``stream.result()`` for the assembled AssistantMessage or stream failure.
    """

    def __call__(
        self, view: ProviderView, *, signal: asyncio.Event | None = None
    ) -> AssistantMessageEventStream: ...


@dataclass(frozen=True)
class PrepareNextTurnResult:
    """Model/provider replacement before a subsequent request in one turn."""

    provider: Provider | None = None
    model: str | None = None


__all__ = [
    "Provider",
    "SessionLike",
    "PrepareNextTurnResult",
    "ProviderView",
    "AgentLoopContext",
    "ExecutionEnv",
    "FileSystem",
    "Shell",
]
