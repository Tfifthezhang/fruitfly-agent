"""Hook registry — active hooks (can modify/block) + passive observers.

Dispatch convention: at every named hook point the loop runs active
handlers first (priority order, return value replaces the event) and then
emits committed-state snapshots to passive observers — both flavors always
fire. Passive observers are awaited for deterministic research telemetry,
but each receives a private deep copy and therefore cannot affect the run.

Isolation guarantee: a failing hook NEVER kills the run. Active-hook
exceptions are recorded as hookError session entries; passive-observer
exceptions are swallowed. Handlers run in registration order.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable

from ..data_model.messages import (
    AgentLoopResult,
    AgentMessage,
    AgentToolResult,
    AssistantMessage,
)

# Lifecycle hook points supported by FruitFlyAgent.
BEFORE_RUN = "before_run"
BEFORE_REQUEST = "before_request"
AFTER_RESPONSE = "after_response"
BEFORE_TOOL = "before_tool"
AFTER_TOOL = "after_tool"
BEFORE_COMPACTION = "before_compaction"
BEFORE_RUN_END = "before_run_end"

HOOK_NAMES = (
    BEFORE_RUN,
    BEFORE_REQUEST,
    AFTER_RESPONSE,
    BEFORE_TOOL,
    AFTER_TOOL,
    BEFORE_COMPACTION,
    BEFORE_RUN_END,
)


@dataclass
class BeforeRunEvent:
    messages: list[AgentMessage]
    system_prompt: str
    model: str


@dataclass
class BeforeRequestEvent:
    """Mutable payload committed before budgeting and sending the request."""

    system_prompt: str
    messages: list[AgentMessage]
    tools: list[Any]
    model: str
    max_tokens: int


@dataclass
class AfterResponseEvent:
    assistant: AssistantMessage


@dataclass
class ToolEvent:
    tool_name: str
    args: dict
    tool_call_id: str = ""
    block: bool = False
    reason: str = ""
    terminate: bool = False


@dataclass
class AfterToolEvent:
    tool_name: str
    args: dict
    result: AgentToolResult
    tool_call_id: str = ""


@dataclass
class BeforeCompactionEvent:
    """A Core-owned commit event for a Lab-proposed model projection."""

    messages: list[AgentMessage]
    estimated_tokens: int
    trigger: str
    mechanism_id: str
    metadata: dict[str, Any]
    cancel: bool = False


@dataclass
class BeforeRunEndEvent:
    result: AgentLoopResult


@dataclass(frozen=True)
class _Handler:
    fn: Callable[[Any], Any]
    active: bool
    priority: int


class HookRegistry:
    def __init__(self, session: Any | None = None) -> None:
        self._handlers: dict[str, list[_Handler]] = {name: [] for name in HOOK_NAMES}
        self._session = session

    # -- registration -------------------------------------------------------

    def add(self, name: str, fn: Callable[[Any], Any], *, priority: int = 100) -> None:
        """Register an ACTIVE hook: may mutate or block via the event object."""
        if name not in self._handlers:
            raise ValueError(f"unknown hook name {name!r}; known: {', '.join(HOOK_NAMES)}")
        self._handlers[name].append(_Handler(fn=fn, active=True, priority=priority))
        self._handlers[name].sort(key=lambda h: h.priority)

    def on(self, name: str, fn: Callable[[Any], Any]) -> None:
        """Register a PASSIVE observer that receives an isolated snapshot."""
        if name not in self._handlers:
            raise ValueError(f"unknown hook name {name!r}; known: {', '.join(HOOK_NAMES)}")
        self._handlers[name].append(_Handler(fn=fn, active=False, priority=100))

    def clone(self) -> "HookRegistry":
        """Copy registrations so a derived config cannot mutate its parent."""
        cloned = HookRegistry(session=self._session)
        cloned._handlers = {name: list(handlers) for name, handlers in self._handlers.items()}
        return cloned

    # -- dispatch -----------------------------------------------------------

    async def run(self, name: str, event: Any) -> Any:
        """Run active handlers in priority order; returns the (possibly mutated) event.

        Per-hook exception isolation: a failing hook is recorded as a
        hookError session entry and never propagates.
        """
        for handler in list(self._handlers.get(name, [])):
            if not handler.active:
                continue
            try:
                candidate = copy.deepcopy(event)
                result = handler.fn(candidate)
                if hasattr(result, "__await__"):
                    result = await result
                result = candidate if result is None else result
                if not isinstance(result, type(event)):
                    raise TypeError(
                        f"hook {name!r} returned {type(result).__name__}; "
                        f"expected {type(event).__name__} or None"
                    )
                event = result
            except Exception as exc:  # noqa: BLE001 — the isolation guarantee
                self._record_hook_error(name, exc)
        return event

    async def emit(self, name: str, event: Any) -> None:
        """Run passive observers on private snapshots; exceptions swallowed."""
        for handler in list(self._handlers.get(name, [])):
            if handler.active:
                continue
            try:
                result = handler.fn(copy.deepcopy(event))
                if hasattr(result, "__await__"):
                    await result
            except Exception:  # noqa: BLE001
                pass

    # -- internals ----------------------------------------------------------

    def _record_hook_error(self, name: str, exc: Exception) -> None:
        try:
            if self._session is not None:
                self._session.append(
                    "meta",
                    {"kind": "hookError", "hook": name, "error": f"{type(exc).__name__}: {exc}"},
                )
        except Exception:  # noqa: BLE001 — session write failure never kills the run
            pass

    def __contains__(self, name: str) -> bool:
        return bool(self._handlers.get(name))


__all__ = [
    "HookRegistry",
    "BEFORE_RUN",
    "BEFORE_REQUEST",
    "AFTER_RESPONSE",
    "BEFORE_TOOL",
    "AFTER_TOOL",
    "BEFORE_COMPACTION",
    "BEFORE_RUN_END",
    "BeforeRunEvent",
    "BeforeRequestEvent",
    "AfterResponseEvent",
    "ToolEvent",
    "AfterToolEvent",
    "BeforeCompactionEvent",
    "BeforeRunEndEvent",
]
