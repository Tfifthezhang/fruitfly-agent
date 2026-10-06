"""Serializable messages, content blocks, usage, and operation results.

Serialization contract: every message type round-trips through
``to_dict`` / ``from_dict`` exactly. This is the session-log format.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Content blocks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TextBlock:
    text: str
    type: str = "text"

    def to_dict(self) -> dict[str, Any]:
        return {"type": "text", "text": self.text}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TextBlock":
        return cls(text=str(d.get("text") or ""))


@dataclass(frozen=True)
class ThinkingBlock:
    thinking: str
    type: str = "thinking"

    def to_dict(self) -> dict[str, Any]:
        return {"type": "thinking", "thinking": self.thinking}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ThinkingBlock":
        return cls(thinking=str(d.get("thinking") or ""))


@dataclass(frozen=True)
class ToolCallBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: str = "toolCall"

    def to_dict(self) -> dict[str, Any]:
        return {"type": "toolCall", "id": self.id, "name": self.name, "input": self.input}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ToolCallBlock":
        raw = d.get("input") or {}
        return cls(
            id=str(d.get("id") or ""),
            name=str(d.get("name") or ""),
            input=raw if isinstance(raw, dict) else {},
        )


@dataclass(frozen=True)
class ImageBlock:
    data: str  # base64-encoded image bytes
    media_type: str
    type: str = "image"

    def to_dict(self) -> dict[str, Any]:
        return {"type": "image", "data": self.data, "media_type": self.media_type}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ImageBlock":
        return cls(
            data=str(d.get("data") or ""),
            media_type=str(d.get("media_type") or ""),
        )


ContentBlock = TextBlock | ThinkingBlock | ToolCallBlock | ImageBlock


def block_from_dict(d: dict[str, Any]) -> ContentBlock:
    t = str(d.get("type") or "")
    if t == "text":
        return TextBlock.from_dict(d)
    if t == "thinking":
        return ThinkingBlock.from_dict(d)
    if t == "toolCall":
        return ToolCallBlock.from_dict(d)
    if t == "image":
        return ImageBlock.from_dict(d)
    return TextBlock(text=str(d))


# ---------------------------------------------------------------------------
# Usage / stop reason
# ---------------------------------------------------------------------------

StopReason = Literal["pending", "stop", "length", "toolUse", "error", "aborted"]


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "cacheReadTokens": self.cache_read_tokens,
            "cacheCreationTokens": self.cache_creation_tokens,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Usage":
        d = d or {}
        return cls(
            input_tokens=int(d.get("inputTokens") or d.get("input_tokens") or 0),
            output_tokens=int(d.get("outputTokens") or d.get("output_tokens") or 0),
            cache_read_tokens=int(d.get("cacheReadTokens") or d.get("cache_read_tokens") or 0),
            cache_creation_tokens=int(
                d.get("cacheCreationTokens") or d.get("cache_creation_tokens") or 0
            ),
        )


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

#: Custom message kinds used by the harness (converted at the LLM boundary).
CUSTOM_KIND_COMPACTION = "compactionSummary"
CUSTOM_KIND_BRANCH = "branchSummary"


@dataclass(frozen=True)
class UserMessage:
    content: str | list[TextBlock | ImageBlock]
    timestamp: float = 0.0
    role: str = "user"

    def to_dict(self) -> dict[str, Any]:
        if isinstance(self.content, str):
            content: Any = self.content
        else:
            content = [b.to_dict() for b in self.content]
        return {"role": "user", "content": content, "timestamp": self.timestamp}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "UserMessage":
        content = d.get("content")
        if isinstance(content, str):
            return cls(content=content, timestamp=float(d.get("timestamp") or 0))
        blocks = [block_from_dict(b) for b in (content or []) if isinstance(b, dict)]
        kept: list[TextBlock | ImageBlock] = []
        for b in blocks:
            if isinstance(b, (TextBlock, ImageBlock)):
                kept.append(b)
        return cls(content=kept, timestamp=float(d.get("timestamp") or 0))


@dataclass(frozen=True)
class AssistantMessage:
    content: list[TextBlock | ThinkingBlock | ToolCallBlock] = field(default_factory=list)
    stop_reason: StopReason = "pending"
    usage: Usage | None = None
    timestamp: float = 0.0
    role: str = "assistant"

    @property
    def tool_calls(self) -> list[ToolCallBlock]:
        return [b for b in self.content if isinstance(b, ToolCallBlock)]

    @property
    def text(self) -> str:
        return "".join(b.text for b in self.content if isinstance(b, TextBlock))

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": [b.to_dict() for b in self.content],
            "stopReason": self.stop_reason,
            "usage": self.usage.to_dict() if self.usage is not None else None,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AssistantMessage":
        content = [block_from_dict(b) for b in (d.get("content") or []) if isinstance(b, dict)]
        kept: list[TextBlock | ThinkingBlock | ToolCallBlock] = [
            b for b in content if isinstance(b, (TextBlock, ThinkingBlock, ToolCallBlock))
        ]
        sr = str(d.get("stopReason") or "pending")
        if sr not in ("pending", "stop", "length", "toolUse", "error", "aborted"):
            sr = "stop"
        usage = d.get("usage")
        return cls(
            content=kept,
            stop_reason=sr,  # type: ignore[arg-type]
            usage=Usage.from_dict(usage) if isinstance(usage, dict) else None,
            timestamp=float(d.get("timestamp") or 0),
        )


@dataclass(frozen=True)
class ToolResultMessage:
    tool_call_id: str
    content: list[TextBlock | ImageBlock] = field(default_factory=list)
    is_error: bool = False
    terminate: bool = False
    timestamp: float = 0.0
    role: str = "toolResult"

    @property
    def text(self) -> str:
        return "".join(b.text for b in self.content if isinstance(b, TextBlock))

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": "toolResult",
            "toolCallId": self.tool_call_id,
            "content": [b.to_dict() for b in self.content],
            "isError": self.is_error,
            "terminate": self.terminate,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ToolResultMessage":
        content = [block_from_dict(b) for b in (d.get("content") or []) if isinstance(b, dict)]
        kept: list[TextBlock | ImageBlock] = [
            b for b in content if isinstance(b, (TextBlock, ImageBlock))
        ]
        return cls(
            tool_call_id=str(d.get("toolCallId") or ""),
            content=kept,
            is_error=bool(d.get("isError")),
            terminate=bool(d.get("terminate")),
            timestamp=float(d.get("timestamp") or 0),
        )


@dataclass(frozen=True)
class CustomMessage:
    """Harness-internal message; converted to a user message at the LLM boundary."""

    kind: str
    text: str
    timestamp: float = 0.0
    role: str = "custom"

    def to_dict(self) -> dict[str, Any]:
        return {"role": "custom", "kind": self.kind, "text": self.text, "timestamp": self.timestamp}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CustomMessage":
        return cls(
            kind=str(d.get("kind") or "custom"),
            text=str(d.get("text") or ""),
            timestamp=float(d.get("timestamp") or 0),
        )


AgentMessage = UserMessage | AssistantMessage | ToolResultMessage | CustomMessage


def message_from_dict(d: dict[str, Any]) -> AgentMessage:
    role = str(d.get("role") or "")
    if role == "user":
        return UserMessage.from_dict(d)
    if role == "assistant":
        return AssistantMessage.from_dict(d)
    if role == "toolResult":
        return ToolResultMessage.from_dict(d)
    if role == "custom":
        return CustomMessage.from_dict(d)
    raise ValueError(f"unknown message role: {role!r}")


# ---------------------------------------------------------------------------
# Tool results / loop results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentToolResult:
    content: list[TextBlock | ImageBlock] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    terminate: bool = False

    @classmethod
    def error(cls, message: str, *, terminate: bool = False) -> "AgentToolResult":
        return cls(content=[TextBlock(text=message)], details={}, terminate=terminate)


@dataclass(frozen=True)
class AgentLoopResult:
    messages: list[AgentMessage]
    stop_reason: StopReason
    model: str = ""
    turn_count: int = 0
    tool_call_count: int = 0
    usage: Usage = field(default_factory=Usage)
    is_error: bool = False
    error_details: dict[str, Any] | None = None
    canonical_messages: list[AgentMessage] = field(default_factory=list)


def encode_image_bytes(data: bytes, media_type: str) -> ImageBlock:
    return ImageBlock(data=base64.b64encode(data).decode("ascii"), media_type=media_type)


__all__ = [
    "TextBlock",
    "ThinkingBlock",
    "ToolCallBlock",
    "ImageBlock",
    "ContentBlock",
    "block_from_dict",
    "StopReason",
    "Usage",
    "CUSTOM_KIND_COMPACTION",
    "CUSTOM_KIND_BRANCH",
    "UserMessage",
    "AssistantMessage",
    "ToolResultMessage",
    "CustomMessage",
    "AgentMessage",
    "message_from_dict",
    "AgentToolResult",
    "AgentLoopResult",
    "encode_image_bytes",
]
