"""Ephemeral runtime data shared by the loop and research protocols.

AgentLoopContext is shared by the loop and extension protocols without an
import cycle. ``messages.py`` has no internal imports; this module may depend
on tool, environment, and Session contracts.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ..env.protocols import ExecutionEnv
from ..session.protocol import SessionLike
from ..tool_runtime import AgentTool
from .context import ContextItem
from .messages import AgentMessage, Usage


@dataclass
class AgentLoopContext:
    """Mutable loop-owned state passed to ordinary extension callbacks.

    Compactors do not receive this object.  They receive a frozen
    :class:`ContextSnapshot`, so only Core can commit a model projection.
    """

    system_prompt: str
    messages: list[AgentMessage]
    tools: list[AgentTool]
    env: ExecutionEnv | None
    session: SessionLike | None
    context_window: int
    max_context_recovery_attempts: int
    model: str
    max_tokens: int
    usage: Usage = field(default_factory=Usage)
    canonical_items: list[ContextItem] = field(default_factory=list)
    last_input_tokens: int | None = None
    overflow_attempt: int = 0
    session_run_id: str | None = None
    provider_attempt_count: int = 0
    provider_failure_count: int = 0
    turn_count: int = 0
    tool_call_count: int = 0
    signal: asyncio.Event | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class ProviderView:
    """The request context shared by all implementations of the Provider protocol."""

    system_prompt: str
    messages: list[AgentMessage]
    tools: list[AgentTool]
    model: str
    max_tokens: int = 0


@dataclass(frozen=True)
class BeforeToolCallResult:
    block: bool = False
    reason: str = ""
    terminate: bool = False


__all__ = [
    "AgentLoopContext",
    "ProviderView",
    "BeforeToolCallResult",
]
