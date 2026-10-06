"""Stable data contract between Core context management and Lab algorithms.

Lab receives an immutable snapshot and returns a declarative decision.  Core
alone applies the decision to the live model projection and durable session.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from .messages import AgentMessage

if TYPE_CHECKING:
    from ..tool_runtime import AgentTool

ContextTrigger = Literal["budget", "overflow"]


@dataclass(frozen=True)
class ContextItem:
    """One canonical transcript item with an identity stable across projections."""

    id: str
    message: AgentMessage


@dataclass(frozen=True)
class ContextSnapshot:
    """Read-only input supplied to a compaction algorithm."""

    canonical_items: tuple[ContextItem, ...]
    messages: tuple[AgentMessage, ...]
    system_prompt: str
    tools: tuple[AgentTool, ...]
    context_window: int
    model: str
    max_tokens: int
    trigger: ContextTrigger
    last_input_tokens: int | None = None
    overflow_attempt: int = 0
    signal: asyncio.Event | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class ContextDecision:
    """A proposed model-context projection; it has no side effects by itself.

    ``messages`` is ``None`` when a strategy has no proposal. ``retry`` is
    meaningful for overflow handling. Strategies never construct terminal
    overflow errors; Core owns that stable failure contract.
    """

    messages: tuple[AgentMessage, ...] | None = None
    retry: bool = False
    mechanism_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    estimated_tokens_before: int | None = None


__all__ = ["ContextTrigger", "ContextItem", "ContextSnapshot", "ContextDecision"]
