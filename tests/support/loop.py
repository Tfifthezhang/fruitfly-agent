"""Shared test helpers: loop runner with a faux provider and counting tools."""
from __future__ import annotations

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock, UserMessage
from tests.support.faux_provider import FauxProvider


def make_tool(name: str = "count", *, terminate: bool = False, execution_mode: str = "parallel"):
    calls: list[dict] = []

    async def execute(ctx):
        calls.append(ctx.args)
        return AgentToolResult(content=[TextBlock(text=f"{name} ok")], terminate=terminate)

    tool = AgentTool(
        name=name,
        label=name,
        description=f"test tool {name}",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
        execute=execute,
        execution_mode=execution_mode,
    )
    return tool, calls


def make_config(provider: FauxProvider, tools=None, **overrides) -> AgentLoopConfig:
    kwargs = dict(
        provider=provider,
        model="test-model",
        tools=tools or [],
    )
    kwargs.update(overrides)
    return AgentLoopConfig(**kwargs)


def run_loop(config: AgentLoopConfig, prompt: str, *, signal=None):
    messages = [UserMessage(content=prompt)]
    return run_agent_loop(config, messages, signal=signal)


async def run_loop_async(config: AgentLoopConfig, prompt: str):
    messages = [UserMessage(content=prompt)]
    return await run_agent_loop(config, messages)


__all__ = ["make_tool", "make_config", "run_loop", "run_loop_async"]
