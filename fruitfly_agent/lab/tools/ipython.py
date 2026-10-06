"""AgentTool adapter for an explicitly injected IPython executor."""

from __future__ import annotations

import asyncio
from typing import Any, Mapping, Protocol

from fruitfly_agent.core.data_model.messages import AgentToolResult, TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool, ToolCallContext


class _ExecutionResult(Protocol):
    status: str
    stdout: str
    stderr: str
    result: str
    error: Mapping[str, Any] | None
    output_reference: str | None
    truncated: bool


class _IpythonExecutor(Protocol):
    async def execute(
        self,
        code: str,
        *,
        signal: asyncio.Event | None = None,
    ) -> _ExecutionResult: ...


def create_ipython_tool(runtime: _IpythonExecutor) -> AgentTool:
    """Adapt an injected persistent executor without owning its lifecycle."""

    async def execute(ctx: ToolCallContext) -> AgentToolResult:
        result = await runtime.execute(ctx.args["code"], signal=ctx.signal)
        if result.status == "cancelled":
            raise asyncio.CancelledError
        rendered = _render(result)
        if result.status != "ok":
            raise RuntimeError(rendered)
        return AgentToolResult(
            content=[TextBlock(text=rendered)],
            details={
                "status": result.status,
                "truncated": result.truncated,
                "output_reference": result.output_reference,
            },
        )

    return AgentTool(
        name="ipython",
        label="IPython",
        description=(
            "Execute code in this Session's persistent IPython workspace. "
            "Variables and imports survive later ipython calls while the Runtime "
            "is open. Top-level await is supported. Use the preloaded `context` "
            "object for external artifacts and `await llm_query(...)` for bounded "
            "text-only auxiliary model calls. This is not a security sandbox."
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute in the persistent namespace.",
                }
            },
            "required": ["code"],
            "additionalProperties": False,
        },
        execute=execute,
        execution_mode="sequential",
    )


def _render(result: _ExecutionResult) -> str:
    sections: list[str] = []
    if result.stdout:
        sections.append(result.stdout.rstrip())
    if result.stderr:
        sections.append("stderr:\n" + result.stderr.rstrip())
    if result.result and result.result not in result.stdout:
        sections.append("result:\n" + result.result)
    if result.error:
        sections.append(
            "error:\n"
            + str(result.error.get("type") or "Error")
            + ": "
            + str(result.error.get("message") or "execution failed")
        )
    if result.output_reference:
        sections.append(
            "[output truncated; full output stored at "
            f"{result.output_reference}; read it with context.read(...)]"
        )
    return "\n\n".join(sections) or "Execution completed without output."


__all__ = ["create_ipython_tool"]
