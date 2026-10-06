"""Stable tool declarations used by the Core execution pipeline.

A tool is a plain dataclass: schema-declared, env-injected, and it THROWS on
failure (the loop converts every exception into an error tool result — tools
never need to encode errors in their content).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..data_model.messages import AgentToolResult
from ..env.protocols import ExecutionEnv


@dataclass(frozen=True)
class ToolCallContext:
    tool_call_id: str
    name: str
    args: dict[str, Any]  # post-prepareArguments, post-validation, coerced
    env: ExecutionEnv | None
    on_update: Callable[[str], Awaitable[None]] | None = None
    signal: asyncio.Event | None = None


@dataclass(frozen=True)
class AgentTool:
    name: str
    label: str
    description: str
    parameters: dict[str, Any]  # JSON Schema (draft-07 subset)
    execute: Callable[[ToolCallContext], Awaitable[AgentToolResult] | AgentToolResult]
    prepare_arguments: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    execution_mode: str = "parallel"  # "parallel" | "sequential"
    hide_from_model: bool = False

    def to_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


__all__ = [
    "AgentTool",
    "ToolCallContext",
]
