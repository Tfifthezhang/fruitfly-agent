"""Serializable, renderer-neutral events for interactive frontends."""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if dataclasses.is_dataclass(value):
        return _json_safe(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return repr(value)


@dataclass(frozen=True, kw_only=True)
class FrontendEvent:
    """Serializable frontend event with run identity and ordering metadata."""

    event_type: ClassVar[str] = "event"
    run_id: str
    sequence: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.event_type, **_json_safe(dataclasses.asdict(self))}


@dataclass(frozen=True, kw_only=True)
class RunStarted(FrontendEvent):
    event_type: ClassVar[str] = "run_started"
    prompt: str
    model: str
    message_count: int


@dataclass(frozen=True, kw_only=True)
class RunActivityChanged(FrontendEvent):
    """Replace the current observable activity for one active run."""

    event_type: ClassVar[str] = "run_activity_changed"
    phase: str
    request_index: int = 0
    subject: str = ""
    activity_id: str = ""


@dataclass(frozen=True, kw_only=True)
class AssistantTextDelta(FrontendEvent):
    event_type: ClassVar[str] = "assistant_text_delta"
    text: str


@dataclass(frozen=True, kw_only=True)
class AssistantThinkingDelta(FrontendEvent):
    event_type: ClassVar[str] = "assistant_thinking_delta"
    text: str


@dataclass(frozen=True, kw_only=True)
class ToolStarted(FrontendEvent):
    event_type: ClassVar[str] = "tool_started"
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    category: str = "tools"


@dataclass(frozen=True, kw_only=True)
class ToolOutput(FrontendEvent):
    event_type: ClassVar[str] = "tool_output"
    text: str


@dataclass(frozen=True, kw_only=True)
class ToolFinished(FrontendEvent):
    event_type: ClassVar[str] = "tool_finished"
    tool_call_id: str
    tool_name: str
    output: str
    terminate: bool
    category: str = "tools"


@dataclass(frozen=True, kw_only=True)
class CompactionStarted(FrontendEvent):
    event_type: ClassVar[str] = "compaction_started"
    estimated_tokens: int
    mechanism_id: str
    trigger: str


@dataclass(frozen=True, kw_only=True)
class RunFinished(FrontendEvent):
    event_type: ClassVar[str] = "run_finished"
    stop_reason: str
    model: str
    turn_count: int
    tool_call_count: int
    input_tokens: int
    output_tokens: int
    is_error: bool
    error_details: dict[str, Any] | None


InteractiveEvent = (
    RunStarted
    | RunActivityChanged
    | AssistantTextDelta
    | AssistantThinkingDelta
    | ToolStarted
    | ToolOutput
    | ToolFinished
    | CompactionStarted
    | RunFinished
)


_EVENT_TYPES = {
    event.event_type: event
    for event in (
        RunStarted,
        RunActivityChanged,
        AssistantTextDelta,
        AssistantThinkingDelta,
        ToolStarted,
        ToolOutput,
        ToolFinished,
        CompactionStarted,
        RunFinished,
    )
}


def event_from_dict(payload: Mapping[str, Any]) -> InteractiveEvent:
    """Reconstruct the ordinary frontend event after a process boundary."""

    event_type = payload.get("type")
    cls = _EVENT_TYPES.get(event_type)
    if cls is None:
        raise ValueError(f"unknown interactive event type: {event_type!r}")
    fields = {field.name for field in dataclasses.fields(cls)}
    values = {key: value for key, value in payload.items() if key in fields}
    return cls(**values)


__all__ = [
    "FrontendEvent",
    "RunStarted",
    "RunActivityChanged",
    "AssistantTextDelta",
    "AssistantThinkingDelta",
    "ToolStarted",
    "ToolOutput",
    "ToolFinished",
    "CompactionStarted",
    "RunFinished",
    "InteractiveEvent",
    "event_from_dict",
]
