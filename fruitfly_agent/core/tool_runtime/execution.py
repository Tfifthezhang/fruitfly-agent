"""Execute validated tool batches with hook isolation and cancellation."""

from __future__ import annotations

import asyncio
from typing import Any

from ..config import AgentLoopConfig
from ..data_model.messages import AgentToolResult, AssistantMessage, TextBlock, ToolResultMessage
from ..data_model.runtime import AgentLoopContext, BeforeToolCallResult
from ..extensions.callbacks import call_extension
from ..extensions.hooks import AFTER_TOOL, BEFORE_TOOL, AfterToolEvent, HookRegistry, ToolEvent
from . import ToolCallContext
from .schema import validate_tool_arguments


def _error_result(call_id: str, message: str, *, terminate: bool = False) -> ToolResultMessage:
    return ToolResultMessage(tool_call_id=call_id, content=[TextBlock(message)],
                             is_error=True, terminate=terminate)


async def execute_tool_batch(
    ctx: AgentLoopContext,
    assistant: AssistantMessage,
    config: AgentLoopConfig,
    hooks: HookRegistry,
    signal: asyncio.Event | None,
    *,
    max_calls: int,
) -> tuple[list[ToolResultMessage], bool]:
    calls = assistant.tool_calls[:max_calls]
    names = {tc.name for tc in calls}
    sequential = config.tool_execution.default_execution_mode == "sequential" or any(
        t.execution_mode == "sequential" for t in ctx.tools if t.name in names
    )
    semaphore = asyncio.Semaphore(max(1, config.tool_execution.max_parallel))

    async def run_one(tc) -> ToolResultMessage:
        async with semaphore:
            return await _execute_one(ctx, tc, config, hooks, signal)

    if sequential:
        results = [await run_one(tc) for tc in calls]
    else:
        results = list(await asyncio.gather(*(run_one(tc) for tc in calls)))
    results.extend(
        ToolResultMessage(
            tool_call_id=call.id,
            content=[TextBlock(f"Tool call budget exceeded ({config.max_tool_calls_per_turn}); tool was not executed.")],
            is_error=True,
        )
        for call in assistant.tool_calls[max_calls:]
    )
    return results, bool(results) and all(r.terminate for r in results)


async def _execute_one(
    ctx: AgentLoopContext,
    tc: Any,
    config: AgentLoopConfig,
    hooks: HookRegistry,
    signal: asyncio.Event | None,
) -> ToolResultMessage:
    tool = next((t for t in ctx.tools if t.name == tc.name), None)
    if tool is None:
        return _error_result(tc.id, f'Tool {tc.name} not found')

    args = dict(tc.input)
    if tool.prepare_arguments is not None:
        try:
            args = tool.prepare_arguments(args)
        except Exception as exc:  # noqa: BLE001
            return _error_result(tc.id, f'Argument preparation failed: {exc}')

    validated = validate_tool_arguments(tool.parameters, args)
    if not validated.is_ok:
        return _error_result(tc.id, validated.error or 'invalid arguments')
    args = validated.unwrap()

    # --- before_tool: config callback + hook (block → error result) ---
    # failure default: None → proceed unblocked
    before = None
    if config.before_tool_call is not None:
        before = await call_extension(
            config.before_tool_call,
            ToolCallContext(tc.id, tool.name, args, ctx.env, None, signal),
            label="before_tool_call",
            default=None,
        )
        before = before or BeforeToolCallResult()
    tool_event = ToolEvent(
        tool_name=tool.name,
        args=args,
        tool_call_id=tc.id,
        block=bool(before and before.block),
        reason=before.reason if before else "",
        terminate=bool(before and before.terminate),
    )
    tool_event = await hooks.run(BEFORE_TOOL, tool_event)
    args = dict(tool_event.args)
    revalidated = validate_tool_arguments(tool.parameters, args)
    if not revalidated.is_ok:
        return _error_result(tc.id, revalidated.error or 'invalid arguments after before_tool hook')
    args = revalidated.unwrap()
    tool_event.args = args
    await hooks.emit(BEFORE_TOOL, tool_event)
    if tool_event.block:
        return _error_result(tc.id, tool_event.reason or f'Tool {tool.name} execution was blocked', terminate=tool_event.terminate)

    # Ordinary execution exceptions become error results; cancellation propagates.
    async def on_update(text: str) -> None:
        if config.on_partial is not None:
            await call_extension(config.on_partial, text, label="on_partial", default=None)

    try:
        result = tool.execute(ToolCallContext(tc.id, tool.name, args, ctx.env, on_update, signal))
        if hasattr(result, "__await__"):
            result = await result
    except Exception as exc:  # noqa: BLE001
        return _error_result(tc.id, f'{type(exc).__name__}: {exc}')
    if not isinstance(result, AgentToolResult):
        return _error_result(tc.id, f'Tool {tool.name} returned {type(result).__name__}; expected AgentToolResult')

    # --- after_tool: rewrite hooks ---
    # failure default: None → keep the original result
    if config.after_tool_call is not None:
        rewritten = await call_extension(
            config.after_tool_call,
            ToolCallContext(tc.id, tool.name, args, ctx.env, None, signal),
            result,
            label="after_tool_call",
            default=None,
        )
        if rewritten is not None:
            result = rewritten
    after_event = await hooks.run(
        AFTER_TOOL,
        AfterToolEvent(
            tool_name=tool.name,
            args=args,
            result=result,
            tool_call_id=tc.id,
        ),
    )
    result = after_event.result
    await hooks.emit(AFTER_TOOL, after_event)

    return ToolResultMessage(
        tool_call_id=tc.id,
        content=list(result.content),
        is_error=False,
        terminate=result.terminate,
    )
