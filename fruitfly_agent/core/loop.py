"""Run FruitFlyAgent requests, tools, and bounded context recovery.

Tool lookup, argument, blocking, and execution failures become error tool
results. Provider failures enter context recovery or end with a structured
AgentLoopResult. A response with stop_reason="length" does not execute its
tool calls; each receives an error result. A tool batch terminates only when
every result requests termination.

Ordinary callback failures use the defaults documented at their call sites.
Task cancellation propagates. See README.md for runtime rules and the owning
module guides for hook, context, and Session contracts.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
import uuid
from typing import Any

from .config import AgentLoopConfig
from .context_runtime import (
    append_message as _append,
    check_budget as _check_budget,
    initialize_context_items,
    is_context_overflow,
    recover_from_overflow,
)
from .context import ContextPipeline, ContextReducer
from .data_model.runtime import AgentLoopContext, ProviderView
from .errors import FatalError, OverflowError, RetryableError
from .extensions.hooks import (
    AFTER_RESPONSE,
    BEFORE_REQUEST,
    BEFORE_RUN,
    BEFORE_RUN_END,
    AfterResponseEvent,
    BeforeRequestEvent,
    BeforeRunEndEvent,
    BeforeRunEvent,
    HookRegistry,
)
from .extensions.protocols import Provider
from .tool_runtime.execution import execute_tool_batch
from .extensions.callbacks import call_extension
from .data_model.messages import (
    AgentLoopResult,
    AgentMessage,
    AssistantMessage,
    StopReason,
    TextBlock,
    ToolResultMessage,
    Usage,
)

logger = logging.getLogger(__name__)

_MAX_CONSECUTIVE_TRUNCATED_RESPONSES = 3

_TRUNCATED_TOOL_ERROR = (
    "Tool call {name} was NOT executed: the response hit the output token limit, "
    "so its arguments may be truncated. Re-issue the tool call with complete arguments."
)


async def run_agent_loop(
    config: AgentLoopConfig,
    messages: list[AgentMessage],
    *,
    signal: asyncio.Event | None = None,
    context_pipeline: ContextPipeline | ContextReducer | None = None,
) -> AgentLoopResult:
    """Return structured loop failures; propagate task cancellation."""
    canonical_items = initialize_context_items(config.session, messages)
    ctx = AgentLoopContext(
        system_prompt=config.system_prompt,
        messages=list(messages),
        tools=list(config.tools or []),
        env=config.env,
        session=config.session,
        context_window=config.context_window,
        max_context_recovery_attempts=config.max_context_recovery_attempts,
        model=config.model,
        max_tokens=config.max_tokens,
        canonical_items=canonical_items,
        signal=signal,
    )
    try:
        return await _run(config, ctx, signal, context_pipeline)
    except asyncio.CancelledError:
        _record_run_end(ctx, AgentLoopResult(
            messages=ctx.messages, stop_reason="aborted", model=ctx.model, usage=ctx.usage,
        ))
        raise
    except Exception as exc:  # noqa: BLE001 — return unexpected loop failures
        logger.error("agent loop crashed: %s", exc, exc_info=True)
        result = AgentLoopResult(
            messages=ctx.messages,
            stop_reason="error",
            canonical_messages=[item.message for item in ctx.canonical_items],
            model=ctx.model,
            turn_count=0,
            tool_call_count=0,
            usage=ctx.usage,
            is_error=True,
            error_details={
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "model": ctx.model,
                "context_window": ctx.context_window,
            },
        )
        _record_run_end(ctx, result)
        return result


async def _run(
    config: AgentLoopConfig,
    ctx: AgentLoopContext,
    signal: asyncio.Event | None,
    context_pipeline: ContextPipeline | ContextReducer | None,
) -> AgentLoopResult:
    hooks = config.hooks or HookRegistry(session=ctx.session)
    provider = config.provider

    # --- before_run: generic run-boundary extension point ---
    event = await hooks.run(
        BEFORE_RUN, BeforeRunEvent(messages=ctx.messages, system_prompt=ctx.system_prompt, model=ctx.model)
    )
    ctx.messages = event.messages
    ctx.system_prompt = event.system_prompt
    ctx.model = event.model
    ctx.session_run_id = uuid.uuid4().hex
    _append_session_record(
        ctx,
        "start",
        {"model": ctx.model, "initial_message_count": len(ctx.messages)},
    )
    await hooks.emit(
        BEFORE_RUN, BeforeRunEvent(messages=ctx.messages, system_prompt=ctx.system_prompt, model=ctx.model)
    )

    turn_count = 0
    tool_call_count = 0
    truncated_responses = 0

    # Outer loop: turns (steering + follow-up can extend a turn).
    while turn_count < config.max_turns:
        if _aborted(signal):
            return await _finish(config, ctx, hooks, "aborted", turn_count, tool_call_count)
        turn_count += 1
        turn_tool_call_count = 0

        follow_up_used = False
        first_iteration = True
        # Inner loop: tool calls until the model stops calling tools.
        while True:
            if _aborted(signal):
                return await _finish(config, ctx, hooks, "aborted", turn_count, tool_call_count)

            # --- prepare_next_turn: per-request context/model swap ---
            # failure default: None → no swap this iteration
            if not first_iteration and config.prepare_next_turn is not None:
                prepared = await call_extension(config.prepare_next_turn, ctx, label="prepare_next_turn", default=None)
                if prepared is not None:
                    if prepared.model:
                        ctx.model = prepared.model
                    if prepared.provider is not None:
                        provider = prepared.provider

            # Steering messages injected before the next assistant response
            # (the callback must drain — return each message once).
            # failure default: [] → nothing injected
            if config.get_steering_messages is not None:
                for message in await call_extension(
                    config.get_steering_messages,
                    ctx,
                    label="get_steering_messages",
                    default=[],
                ):
                    _append(ctx, message)
            first_iteration = False

            # Re-check after callbacks — an abort set during prepare_next_turn
            # or steering must prevent the next request.
            if _aborted(signal):
                return await _finish(config, ctx, hooks, "aborted", turn_count, tool_call_count)

            # --- request preparation ---
            # Active changes are committed to ctx before budgeting so the
            # reducer and provider see the same prompt/messages/tools/model.
            request_ctx = _request_ctx(ctx)
            request_event = await hooks.run(BEFORE_REQUEST, request_ctx)
            ctx.system_prompt = request_event.system_prompt
            ctx.messages = list(request_event.messages)
            ctx.tools = list(request_event.tools)
            ctx.model = request_event.model
            ctx.max_tokens = request_event.max_tokens
            await hooks.emit(BEFORE_REQUEST, request_event)

            # Core owns the fixed context order. Generic request hooks run first;
            # Lab transformations then prepare the final projection for budgeting.
            if isinstance(context_pipeline, ContextPipeline):
                await context_pipeline.prepare(ctx)

            # --- reduction budget check before every Provider request ---
            await _check_budget(ctx, hooks, context_pipeline)
            if _aborted(signal):
                return await _finish(config, ctx, hooks, "aborted", turn_count, tool_call_count)

            # Rebuild after compaction because it may replace ctx.messages.
            request_ctx = _request_ctx(ctx)

            ctx.provider_attempt_count += 1
            assistant = await _stream_once(provider, request_ctx, signal)
            if isinstance(assistant, TaggedFailure):
                handled = await _handle_failure(assistant, ctx, hooks, context_pipeline)
                ctx.provider_failure_count += 1
                _append_session_record(
                    ctx,
                    "provider_attempt_failed",
                    {
                        "attempt": ctx.provider_attempt_count,
                        "model": ctx.model,
                        "error_kind": type(assistant.error).__name__,
                        "error": _bounded_session_text(str(assistant.error)),
                        "disposition": "terminal" if handled is not None else "recovered",
                    },
                )
                if handled is not None:
                    return await _finish(
                        config, ctx, hooks,
                        stop_reason="error",
                        turn_count=turn_count,
                        tool_call_count=tool_call_count,
                        is_error=True,
                        error_details=handled,
                    )
                continue  # ladder handled it: retry this iteration

            response_event = await hooks.run(
                AFTER_RESPONSE, AfterResponseEvent(assistant=assistant)
            )
            assistant = response_event.assistant
            _append(ctx, assistant)
            ctx.last_input_tokens = assistant.usage.input_tokens if assistant.usage else None
            ctx.overflow_attempt = 0
            ctx.usage = Usage(
                input_tokens=ctx.usage.input_tokens + (assistant.usage.input_tokens if assistant.usage else 0),
                output_tokens=ctx.usage.output_tokens + (assistant.usage.output_tokens if assistant.usage else 0),
                cache_read_tokens=ctx.usage.cache_read_tokens + (assistant.usage.cache_read_tokens if assistant.usage else 0),
                cache_creation_tokens=ctx.usage.cache_creation_tokens + (assistant.usage.cache_creation_tokens if assistant.usage else 0),
            )
            await hooks.emit(AFTER_RESPONSE, response_event)

            # Truncated responses must not execute any tool calls in the batch.
            if assistant.stop_reason == "length":
                for tc in assistant.tool_calls:
                    _append(
                        ctx,
                        ToolResultMessage(
                            tool_call_id=tc.id,
                            content=[TextBlock(text=_TRUNCATED_TOOL_ERROR.format(name=tc.name))],
                            is_error=True,
                        ),
                    )
                truncated_responses += 1
                if truncated_responses >= _MAX_CONSECUTIVE_TRUNCATED_RESPONSES:
                    return await _finish(
                        config, ctx, hooks, "error", turn_count, tool_call_count,
                        is_error=True,
                        error_details={
                            "kind": "output_limit",
                            "error": "consecutive truncated response limit reached",
                            "attempts": truncated_responses,
                            "model": ctx.model,
                        },
                    )
                continue

            truncated_responses = 0

            tool_calls = assistant.tool_calls
            if not tool_calls:
                break  # inner loop done; poll follow-up

            remaining = max(0, config.max_tool_calls_per_turn - turn_tool_call_count)
            batch_results, terminate = await execute_tool_batch(
                ctx, assistant, config, hooks, signal, max_calls=remaining,
            )
            executed = min(remaining, len(tool_calls))
            tool_call_count += executed
            turn_tool_call_count += executed
            for result in batch_results:
                _append(ctx, result)
            if terminate:
                return await _finish(config, ctx, hooks, "stop", turn_count, tool_call_count)
            if executed < len(tool_calls):
                break

        # Agent would stop here. Follow-up messages keep it going.
        # failure default: [] → no follow-up
        if config.get_follow_up_messages is not None:
            follow_ups = await call_extension(config.get_follow_up_messages, ctx, label="get_follow_up_messages", default=[])
            if follow_ups:
                for message in follow_ups:
                    _append(ctx, message)
                follow_up_used = True
        if not follow_up_used:
            # failure default: False → continue (the outer loop is bounded by max_turns)
            if config.should_stop_after_turn is not None:
                if await call_extension(config.should_stop_after_turn, ctx, label="should_stop_after_turn", default=False):
                    break
            break

    return await _finish(config, ctx, hooks, "stop", turn_count, tool_call_count)


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


class TaggedFailure:
    """A provider failure carried back from _stream_once."""

    def __init__(self, error: Any) -> None:
        self.error = error


def _request_ctx(ctx: AgentLoopContext) -> BeforeRequestEvent:
    return BeforeRequestEvent(
        system_prompt=ctx.system_prompt,
        messages=list(ctx.messages),
        tools=list(ctx.tools),
        model=ctx.model,
        max_tokens=ctx.max_tokens,
    )


async def _stream_once(provider: Provider, request_ctx: BeforeRequestEvent, signal: asyncio.Event | None):
    """Run one provider stream; returns AssistantMessage or TaggedFailure."""
    # Pass only the public ProviderView fields to the model adapter.
    view = ProviderView(
        system_prompt=request_ctx.system_prompt,
        messages=request_ctx.messages,
        tools=request_ctx.tools,
        model=request_ctx.model,
        max_tokens=request_ctx.max_tokens,
    )
    try:
        stream = provider(view, signal=signal)
        async for event in stream:  # noqa: B007 — drain to the terminal event
            pass
        return await stream.result()
    except asyncio.CancelledError:
        raise
    except OverflowError as exc:
        return TaggedFailure(exc)
    except RetryableError as exc:
        return TaggedFailure(exc)
    except FatalError as exc:
        return TaggedFailure(exc)
    # failure default: any other provider failure (sync call, mid-stream
    # raise from a lab stream, ...) → structured end via the fatal path.
    except Exception as exc:  # noqa: BLE001
        logger.warning("provider failed (isolated): %s", exc)
        return TaggedFailure(FatalError(f"{type(exc).__name__}: {exc}"))


async def _handle_failure(
    failure: TaggedFailure,
    ctx: AgentLoopContext,
    hooks: HookRegistry,
    context_pipeline: ContextPipeline | ContextReducer | None,
) -> dict | None:
    """Route context failures to the context runtime, others to fatal end."""
    error = failure.error
    if is_context_overflow(error, ctx, context_pipeline):
        return await recover_from_overflow(error, ctx, hooks, context_pipeline)
    return {
        "kind": type(error).__name__,
        "error": str(error),
        "model": ctx.model,
    }


async def _finish(
    config: AgentLoopConfig,
    ctx: AgentLoopContext,
    hooks: HookRegistry,
    stop_reason: StopReason,
    turn_count: int,
    tool_call_count: int,
    *,
    is_error: bool = False,
    error_details: dict | None = None,
) -> AgentLoopResult:
    result = AgentLoopResult(
        messages=ctx.messages,
        stop_reason=stop_reason,
        canonical_messages=[item.message for item in ctx.canonical_items],
        model=ctx.model,
        turn_count=turn_count,
        tool_call_count=tool_call_count,
        usage=ctx.usage,
        is_error=is_error,
        error_details=error_details,
    )
    end_event = await hooks.run(BEFORE_RUN_END, BeforeRunEndEvent(result=result))
    result = end_event.result  # active handlers may rewrite the final result
    await hooks.emit(BEFORE_RUN_END, end_event)
    _record_run_end(ctx, result)
    return result


def _record_run_end(ctx: AgentLoopContext, result: AgentLoopResult) -> None:
    _append_session_record(ctx, "end", {
        "stop_reason": result.stop_reason,
        "model": result.model,
        "turn_count": result.turn_count,
        "tool_call_count": result.tool_call_count,
        "provider_attempt_count": ctx.provider_attempt_count,
        "provider_failure_count": ctx.provider_failure_count,
        "usage": result.usage.to_dict(),
        "is_error": result.is_error,
        "error": _session_error(result.error_details),
    })


def _append_session_record(
    ctx: AgentLoopContext,
    event: str,
    data: dict[str, Any],
) -> None:
    if ctx.session is None or ctx.session_run_id is None:
        return
    try:
        ctx.session.append(
            "meta",
            {
                "kind": "runRecord",
                "schema_version": 1,
                "run_id": ctx.session_run_id,
                "event": event,
                "data": data,
            },
        )
    except Exception as exc:  # noqa: BLE001 — persistence must not change run semantics
        logger.warning("session run record append failed: %s", exc)


def _session_error(details: dict | None) -> dict[str, Any] | None:
    if not details:
        return None
    result = {}
    for key in ("kind", "error", "model"):
        if key not in details:
            continue
        value = details[key]
        result[key] = (
            _bounded_session_text(value)
            if isinstance(value, str)
            else value
        )
    return result


def _bounded_session_text(value: str, limit: int = 512) -> str:
    return value if len(value) <= limit else value[:limit] + "…"


def _aborted(signal: asyncio.Event | None) -> bool:
    return signal is not None and signal.is_set()



__all__ = ["run_agent_loop", "AgentLoopContext"]
