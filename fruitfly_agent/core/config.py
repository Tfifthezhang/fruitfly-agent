"""Configuration — the knobs a researcher turns.

Every callback is typed against the core seam vocabulary (data_model /
protocols): the annotation IS the contract. Turn control remains available as
fine-grained callbacks rather than a bundled subsystem.

BeforeToolCallResult / PrepareNextTurnResult are re-exported here for
backward compatibility; they live in data_model.runtime / extensions.protocols.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Sequence

from .data_model.messages import AgentMessage, AgentToolResult
from .data_model.runtime import AgentLoopContext, BeforeToolCallResult
from .env.protocols import ExecutionEnv
from .extensions.hooks import HookRegistry
from .extensions.protocols import PrepareNextTurnResult, Provider, SessionLike
from .tool_runtime import AgentTool, ToolCallContext


@dataclass(frozen=True)
class ToolExecutionConfig:
    max_parallel: int = 8
    default_execution_mode: str = "parallel"  # "parallel" | "sequential"


@dataclass(frozen=True)
class AgentLoopConfig:
    # --- model seam: vendor construction belongs in fruitfly_agent.providers ---
    provider: Provider
    model: str = ""
    max_tokens: int = 4096

    # --- context / rails ---
    system_prompt: str = ""
    context_window: int = 200_000
    max_context_recovery_attempts: int = 6
    max_turns: int = 32
    max_tool_calls_per_turn: int = 64

    # --- the research extension points ---
    prepare_next_turn: (
        Callable[
            [AgentLoopContext],
            Awaitable[PrepareNextTurnResult | None] | PrepareNextTurnResult | None,
        ]
        | None
    ) = None
    get_steering_messages: (
        Callable[
            [AgentLoopContext],
            Awaitable[list[AgentMessage]] | list[AgentMessage],
        ]
        | None
    ) = None
    get_follow_up_messages: (
        Callable[[AgentLoopContext], Awaitable[list[AgentMessage]] | list[AgentMessage]] | None
    ) = None
    should_stop_after_turn: (
        Callable[[AgentLoopContext], Awaitable[bool] | bool] | None
    ) = None
    before_tool_call: (
        Callable[
            [ToolCallContext],
            Awaitable[BeforeToolCallResult | None] | BeforeToolCallResult | None,
        ]
        | None
    ) = None
    after_tool_call: (
        Callable[
            [ToolCallContext, AgentToolResult],
            Awaitable[AgentToolResult | None] | AgentToolResult | None,
        ]
        | None
    ) = None

    # --- subsystems ---
    tool_execution: ToolExecutionConfig = field(default_factory=ToolExecutionConfig)
    hooks: HookRegistry | None = None
    env: ExecutionEnv | None = None
    session: SessionLike | None = None
    tools: Sequence[AgentTool] | None = None

    # --- display ---
    on_partial: Callable[[str], Awaitable[None] | None] | None = None  # tool streaming updates

    def __post_init__(self) -> None:
        for name, minimum in (("max_context_recovery_attempts", 1), ("max_turns", 0),
                              ("max_tool_calls_per_turn", 0)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{name} must be at least {minimum}")
        tools = tuple(self.tools or ())
        names = [tool.name for tool in tools]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate tool names: {', '.join(duplicates)}")
        object.__setattr__(self, "tools", tools)
