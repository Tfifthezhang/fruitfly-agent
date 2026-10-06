"""Provider-neutral model stream events and terminal-result state machine.

Providers translate vendor SDK events into this core-owned vocabulary. The
agent loop consumes only ``AssistantMessageEventStream`` and therefore never
depends on Anthropic, OpenAI, or another provider implementation. Offline
providers and application-specific adapters implement the same contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from .errors import FatalError
from .data_model.messages import AssistantMessage


@dataclass(frozen=True)
class StreamStart:
    pass


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ThinkingDelta:
    thinking: str


@dataclass(frozen=True)
class ToolCallStart:
    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCallDelta:
    json_delta: str


@dataclass(frozen=True)
class ToolCallEnd:
    input: dict[str, Any]


@dataclass(frozen=True)
class StreamDone:
    result: AssistantMessage


@dataclass(frozen=True)
class StreamError:
    error: Exception


StreamEvent = (
    StreamStart
    | TextDelta
    | ThinkingDelta
    | ToolCallStart
    | ToolCallDelta
    | ToolCallEnd
    | StreamDone
    | StreamError
)


class AssistantMessageEventStream:
    """Async-iterable model stream with a terminal ``AssistantMessage``."""

    def __init__(self, iterator: AsyncIterator[StreamEvent]) -> None:
        self._iterator = iterator
        self._final: AssistantMessage | None = None
        self._error: Exception | None = None

    def __aiter__(self) -> "AssistantMessageEventStream":
        return self

    async def __anext__(self) -> StreamEvent:
        event = await self._iterator.__anext__()
        if isinstance(event, StreamDone):
            self._final = event.result
            raise StopAsyncIteration
        if isinstance(event, StreamError):
            self._error = event.error
            raise StopAsyncIteration
        return event

    async def result(self) -> AssistantMessage:
        """Drain remaining events and return the terminal message or error."""
        async for _ in self:
            pass
        if self._error is not None:
            raise self._error
        if self._final is None:
            raise FatalError("stream ended without a terminal event")
        return self._final


async def scripted_stream(
    events: list[StreamEvent], final: AssistantMessage | None = None
) -> AssistantMessageEventStream:
    """Build a stream from scripted events for deterministic implementations."""

    async def gen() -> AsyncIterator[StreamEvent]:
        for event in events:
            yield event
        if final is not None:
            yield StreamDone(result=final)

    return AssistantMessageEventStream(gen())


__all__ = [
    "AssistantMessageEventStream",
    "StreamEvent",
    "StreamStart",
    "TextDelta",
    "ThinkingDelta",
    "ToolCallStart",
    "ToolCallDelta",
    "ToolCallEnd",
    "StreamDone",
    "StreamError",
    "scripted_stream",
]
