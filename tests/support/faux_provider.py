"""Faux provider — scripted assistant responses, zero network.

Shared scripted Provider for offline behavior tests.
"""
from __future__ import annotations
import asyncio
from typing import Any
from fruitfly_agent.core.errors import FatalError, OverflowError, RetryableError
from fruitfly_agent.core.model_stream import (
    AssistantMessageEventStream,
    StreamDone,
    StreamError,
    TextDelta,
)
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock, ToolCallBlock, Usage


class FauxProvider:
    """Scripted responses consumed in order; records every request context."""

    def __init__(self) -> None:
        self.script: list[Any] = []  # AssistantMessage | Exception | callable
        self.calls: list[dict] = []

    def respond(self, message: AssistantMessage) -> None:
        self.script.append(message)

    def respond_text(self, text: str, *, stop_reason: str = "stop") -> None:
        self.respond(
            AssistantMessage(
                content=[TextBlock(text=text)],
                stop_reason=stop_reason,  # type: ignore[arg-type]
                usage=Usage(input_tokens=10, output_tokens=5),
            )
        )

    def respond_tool_call(self, name: str, input: dict, *, stop_reason: str = "toolUse") -> None:
        self.respond(
            AssistantMessage(
                content=[ToolCallBlock(id=f"call_{len(self.script) + 1}", name=name, input=input)],
                stop_reason=stop_reason,  # type: ignore[arg-type]
                usage=Usage(input_tokens=10, output_tokens=5),
            )
        )

    def respond_length_with_tool_call(self, name: str, input: dict) -> None:
        """stopReason == 'length' with a tool call — must never be executed."""
        self.respond_tool_call(name, input, stop_reason="length")

    def respond_overflow(self, message: str = "prompt is too long") -> None:
        self.script.append(OverflowError(message))

    def respond_retryable(self) -> None:
        self.script.append(RetryableError("connection reset"))

    def respond_fatal(self, message: str = "provider exploded", **details: Any) -> None:
        self.script.append(FatalError(message, details=details))

    # -- provider interface ---------------------------------------------------

    def __call__(self, ctx: Any, *, signal: asyncio.Event | None = None) -> AssistantMessageEventStream:
        self.calls.append(
            {
                "system_prompt": ctx.system_prompt,
                "messages": list(ctx.messages),
                "tools": [t.name for t in ctx.tools],
                "model": ctx.model,
                "max_tokens": ctx.max_tokens,
            }
        )
        if not self.script:
            raise AssertionError("faux provider: script exhausted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            return AssistantMessageEventStream(self._error_stream(item))
        if callable(item):
            return item(ctx, signal=signal)
        message: AssistantMessage = item
        return AssistantMessageEventStream(self._message_stream(message))

    @staticmethod
    async def _message_stream(message: AssistantMessage):
        yield TextDelta(text=message.text)
        yield StreamDone(result=message)

    @staticmethod
    async def _error_stream(error: Exception):
        yield StreamError(error=error)


__all__ = ["FauxProvider"]
