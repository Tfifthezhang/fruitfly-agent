"""Core-owned context projection execution and persistence.

This module is deliberately internal.  It keeps compaction coordination out
of the agent loop while Lab remains responsible only for proposing decisions.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .data_model.context import ContextDecision, ContextItem, ContextSnapshot, ContextTrigger
from .data_model.messages import (
    AgentMessage,
    AssistantMessage,
    CustomMessage,
    ToolResultMessage,
    UserMessage,
)
from .data_model.runtime import AgentLoopContext
from .errors import FatalError, OverflowError
from .extensions.hooks import BEFORE_COMPACTION, BeforeCompactionEvent, HookRegistry
from .context import ContextReducer

logger = logging.getLogger(__name__)


def initialize_context_items(session: Any, messages: list[AgentMessage]) -> list[ContextItem]:
    """Restore durable canonical items or seed them for a new session."""

    if session is not None and hasattr(session, "context_items"):
        try:
            items = list(session.context_items())
            if items:
                projected = list(session.messages())
                if len(messages) > len(projected) and messages[: len(projected)] == projected:
                    for message in messages[len(projected) :]:
                        entry = session.append("message", {"message": message.to_dict()})
                        items.append(ContextItem(id=f"session:{entry.id}", message=message))
                return items
            persisted: list[ContextItem] = []
            for message in messages:
                entry = session.append("message", {"message": message.to_dict()})
                persisted.append(ContextItem(id=f"session:{entry.id}", message=message))
            return persisted
        except Exception as exc:  # noqa: BLE001 — session failure never kills the run
            logger.warning("session canonical read failed: %s", exc)
    return [
        ContextItem(id=f"input:{index}", message=message)
        for index, message in enumerate(messages)
    ]


def append_message(ctx: AgentLoopContext, message: AgentMessage) -> None:
    """Append one fact to both the active projection and canonical transcript."""

    ctx.messages.append(message)
    item_id = f"run:{len(ctx.canonical_items) + 1}"
    if ctx.session is not None:
        try:
            entry = ctx.session.append("message", {"message": message.to_dict()})
            if hasattr(entry, "id"):
                item_id = f"session:{entry.id}"
        except Exception as exc:  # noqa: BLE001 — session write never kills the run
            logger.warning("session append failed: %s", exc)
    ctx.canonical_items.append(ContextItem(id=item_id, message=message))


def snapshot(ctx: AgentLoopContext, trigger: ContextTrigger) -> ContextSnapshot:
    """Freeze the current canonical transcript and model projection."""

    return ContextSnapshot(
        canonical_items=tuple(ctx.canonical_items),
        messages=tuple(ctx.messages),
        system_prompt=ctx.system_prompt,
        tools=tuple(ctx.tools),
        context_window=ctx.context_window,
        model=ctx.model,
        max_tokens=ctx.max_tokens,
        trigger=trigger,
        last_input_tokens=ctx.last_input_tokens,
        overflow_attempt=ctx.overflow_attempt,
        signal=ctx.signal,
    )


async def check_budget(
    ctx: AgentLoopContext,
    hooks: HookRegistry,
    reducer: ContextReducer | None,
) -> None:
    """Ask Lab for a pre-request decision and commit it when valid."""

    if reducer is None or ctx.overflow_attempt > 0:
        return
    current = snapshot(ctx, "budget")
    decision = await _call_reducer(
        reducer.check_budget,
        current,
        label="reducer.check_budget",
        default=None,
    )
    if decision is not None:
        await _commit_decision(ctx, hooks, current, decision)


def is_context_overflow(
    error: Exception,
    ctx: AgentLoopContext,
    reducer: ContextReducer | None,
) -> bool:
    """Recognize explicit overflow and guarded unknown-400 overflow."""

    if isinstance(error, OverflowError):
        return True
    return bool(
        isinstance(error, FatalError)
        and error.details
        and error.details.get("unknown_400")
        and reducer is not None
        and _safe_estimate(reducer, ctx) > ctx.context_window
    )


async def recover_from_overflow(
    error: Exception,
    ctx: AgentLoopContext,
    hooks: HookRegistry,
    reducer: ContextReducer | None,
) -> dict[str, Any] | None:
    """Commit a recovery decision; ``None`` means retry the request."""

    if reducer is None:
        return _overflow_details(ctx, str(error))
    if ctx.overflow_attempt >= ctx.max_context_recovery_attempts:
        return _overflow_details(ctx, str(error), recovery="attempt_limit")
    ctx.overflow_attempt += 1
    current = snapshot(ctx, "overflow")
    decision = await _call_reducer(
        reducer.react_to_overflow,
        current,
        error,
        label="reducer.react_to_overflow",
        default=None,
    )
    if decision is None:
        return _overflow_details(ctx, str(error), recovery="unavailable")
    if not isinstance(decision, ContextDecision):
        return _invalid_decision(ctx, decision)
    committed = await _commit_decision(ctx, hooks, current, decision)
    if decision.retry and committed:
        return None
    return _invalid_decision(ctx, decision)


def _safe_estimate(reducer: ContextReducer, ctx: AgentLoopContext) -> int:
    try:
        return reducer.estimate(snapshot(ctx, "overflow"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("reducer.estimate failed (isolated): %s", exc)
        return ctx.context_window + 1


async def _commit_decision(
    ctx: AgentLoopContext,
    hooks: HookRegistry,
    current: ContextSnapshot,
    decision: Any,
) -> bool:
    if not isinstance(decision, ContextDecision) or decision.messages is None:
        if decision is not None and not isinstance(decision, ContextDecision):
            logger.warning(
                "reducer returned %s; expected ContextDecision",
                type(decision).__name__,
            )
        return False
    if not isinstance(decision.messages, tuple):
        logger.warning("reducer returned an internally inconsistent ContextDecision")
        return False
    message_types = (UserMessage, AssistantMessage, ToolResultMessage, CustomMessage)
    if any(not isinstance(message, message_types) for message in decision.messages):
        logger.warning("reducer proposed a projection containing a non-message value")
        return False
    try:
        metadata = dict(decision.metadata)
    except (TypeError, ValueError):
        logger.warning("reducer proposed non-mapping metadata")
        return False

    event = BeforeCompactionEvent(
        messages=list(decision.messages),
        estimated_tokens=(
            decision.estimated_tokens_before
            if isinstance(decision.estimated_tokens_before, int)
            else len(current.messages)
        ),
        trigger=current.trigger,
        mechanism_id=str(decision.mechanism_id),
        metadata=metadata,
    )
    event = await hooks.run(BEFORE_COMPACTION, event)
    if (
        event.cancel
        or not isinstance(event.messages, list)
        or any(not isinstance(message, message_types) for message in event.messages)
        or not isinstance(event.metadata, dict)
    ):
        await hooks.emit(BEFORE_COMPACTION, event)
        return False
    if ctx.session is not None:
        try:
            ctx.session.append(
                "compaction",
                {
                    "messages": [message.to_dict() for message in event.messages],
                    "tokensBefore": event.estimated_tokens,
                    "mechanismId": event.mechanism_id,
                    "trigger": event.trigger,
                    "metadata": event.metadata,
                },
                sync=True,
            )
        except Exception as exc:  # noqa: BLE001 — persistence is isolated
            logger.warning("compaction persistence failed: %s", exc)
    ctx.messages[:] = list(event.messages)
    await hooks.emit(BEFORE_COMPACTION, event)
    return True


async def _call_reducer(fn: Any, *args: Any, label: str, default: Any) -> Any:
    try:
        result = fn(*args)
        if hasattr(result, "__await__"):
            result = await result
        return result
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s failed (isolated): %s", label, exc)
        return default


def _overflow_details(
    ctx: AgentLoopContext, error: str, *, recovery: str | None = None
) -> dict[str, Any]:
    details = {
        "kind": "context_overflow",
        "error": error,
        "model": ctx.model,
        "context_window": ctx.context_window,
        "messages": len(ctx.messages),
        "overflow_attempts": ctx.overflow_attempt,
    }
    if recovery is not None:
        details["recovery"] = recovery
    return details


def _invalid_decision(ctx: AgentLoopContext, decision: Any) -> dict[str, Any]:
    return _overflow_details(ctx, f"invalid reducer decision: {type(decision).__name__}")
