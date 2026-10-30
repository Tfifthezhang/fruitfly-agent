"""Hook registry — active hooks (can modify/block) + passive observers.

Dispatch convention: at every named hook point the loop runs active
handlers first (priority order, return value replaces the event) and then
emits committed-state snapshots to passive observers — both flavors always
fire. Passive observers are awaited for deterministic research telemetry,
but each receives a private deep copy and therefore cannot affect the run.

Optional ordinary failures are isolated. Required active failures and unconfirmed
retirement stop execution. Active errors enter hookError records; optional
observer errors are isolated. Priority order is stable within registrations.
"""

from __future__ import annotations

import copy
import math
from .operations import OperationSupervisor, OperationCleanupError
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
REQUEST_PREPARED = "request_prepared"
AFTER_RESPONSE = "after_response"
BEFORE_TOOL = "before_tool"
AFTER_TOOL = "after_tool"
BEFORE_COMPACTION = "before_compaction"
BEFORE_RUN_END = "before_run_end"

HOOK_NAMES = (
    BEFORE_RUN,
    BEFORE_REQUEST,
    REQUEST_PREPARED,
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
    receipt_timestamp: float | None = None


@dataclass(frozen=True)
class RequestPreparedEvent:
    """Observation of the final projection; does not run active handlers."""

    model: str
    context_window: int
    max_tokens: int
    estimated_tokens: int | None
    estimate_source: str
    timestamp: float


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
    required: bool = False
    timeout: float = 10

    def __post_init__(self):
        if isinstance(self.timeout, bool) or not isinstance(self.timeout, (int, float)) or not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError('hook timeout must be finite and positive')


class HookRegistry:
    def __init__(self, session: Any | None = None) -> None:
        self._handlers: dict[str, list[_Handler]] = {name: [] for name in HOOK_NAMES}
        self._session = session
        self._supervisor = OperationSupervisor()

    # -- registration -------------------------------------------------------

    def add(self, name: str, fn: Callable[[Any], Any], *, priority: int = 100, required: bool = False, timeout: float = 10) -> None:
        """Register an ACTIVE hook: may mutate or block via the event object."""
        if type(required) is not bool:
            raise TypeError('required must be boolean')
        if name == REQUEST_PREPARED:
            raise ValueError("request_prepared is observation-only; use on()")
        if name not in self._handlers:
            raise ValueError(f"unknown hook name {name!r}; known: {', '.join(HOOK_NAMES)}")
        self._handlers[name].append(_Handler(fn=fn, active=True, priority=priority, required=required, timeout=timeout))
        self._handlers[name].sort(key=lambda h: h.priority)

    def on(self, name: str, fn: Callable[[Any], Any], *, timeout: float = 10) -> None:
        """Register a PASSIVE observer that receives an isolated snapshot."""
        if name not in self._handlers:
            raise ValueError(f"unknown hook name {name!r}; known: {', '.join(HOOK_NAMES)}")
        self._handlers[name].append(_Handler(fn=fn, active=False, priority=100, timeout=timeout))

    def clone(self) -> "HookRegistry":
        """Copy registrations so a derived config cannot mutate its parent."""
        cloned = HookRegistry(session=self._session)
        cloned._handlers = {name: list(handlers) for name, handlers in self._handlers.items()}
        return cloned

    # -- dispatch -----------------------------------------------------------

    def extended(self, other: "HookRegistry") -> "HookRegistry":
        cloned = self.clone()
        for name in HOOK_NAMES:
            cloned._handlers[name].extend(other._handlers[name])
            cloned._handlers[name].sort(key=lambda h: h.priority)
        return cloned

    async def run(self, name: str, event: Any) -> Any:
        """Run active handlers in priority order; returns the (possibly mutated) event.

        Optional failures are recorded and isolated. Required failures propagate;
        unconfirmed cancellation always stops execution.
        """
        for handler in list(self._handlers.get(name, [])):
            if not handler.active:
                continue
            try:
                candidate = copy.deepcopy(event)
                result = await self._supervisor.run(lambda: handler.fn(candidate), timeout=handler.timeout)
                result = candidate if result is None else result
                if not isinstance(result, type(event)):
                    raise TypeError(
                        f"hook {name!r} returned {type(result).__name__}; "
                        f"expected {type(event).__name__} or None"
                    )
                event = result
            except OperationCleanupError:
                raise
            except Exception as exc:
                self._record_hook_error(name, exc)
                if handler.required:
                    raise RuntimeError('required hook failed: ' + name) from exc
        return event

    async def emit(self, name: str, event: Any) -> None:
        """Observe private snapshots; isolate ordinary failures and preserve cleanup errors."""
        for handler in list(self._handlers.get(name, [])):
            if handler.active:
                continue
            try:
                await self._supervisor.run(lambda: handler.fn(copy.deepcopy(event)), timeout=handler.timeout)
            except OperationCleanupError:
                raise
            except Exception:
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
    "REQUEST_PREPARED",
    "AFTER_RESPONSE",
    "BEFORE_TOOL",
    "AFTER_TOOL",
    "BEFORE_COMPACTION",
    "BEFORE_RUN_END",
    "BeforeRunEvent",
    "BeforeRequestEvent",
    "AfterResponseEvent",
    "RequestPreparedEvent",
    "ToolEvent",
    "AfterToolEvent",
    "BeforeCompactionEvent",
    "BeforeRunEndEvent",
]
