"""Renderer-neutral read models exposed by the interactive application."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ConversationBlock:
    """Immutable display content; never contains image bytes or tool arguments."""

    kind: Literal["text", "image", "thinking", "tool_call"]
    text: str = ""


@dataclass(frozen=True)
class ConversationMessage:
    """One canonical message projected for frontend history display."""

    role: Literal["user", "assistant", "tool"]
    content: tuple[ConversationBlock, ...]
    tool_name: str = ""
    is_error: bool = False


@dataclass(frozen=True)
class InteractiveMechanism:
    """Renderer-neutral identity for one mechanism active in this session."""

    mechanism_id: str
    category: str
    label: str
    layer: str = "online"
    family: str = "context"
    context_phase: str | None = None
    display_section: str | None = None


@dataclass(frozen=True)
class ResumableSession:
    """Renderer-neutral metadata for one compatible persisted session."""

    path: str
    modified_at: float
    message_count: int
    profile: str
    model: str
    prompt_label: str = ""
    prompt_hash: str = ""


@dataclass(frozen=True)
class InteractiveStatus:
    model: str
    working_directory: str
    session_path: str
    message_count: int
    tool_names: tuple[str, ...]
    mechanisms: tuple[str, ...]
    mechanism_details: tuple[InteractiveMechanism, ...] = ()
    application_state: str = "idle"
    pending_count: int = 0
    prompt_label: str = ""
    prompt_hash: str = ""
    context_window: int | None = None
    max_output_tokens: int | None = None
    estimated_input_tokens: int | None = None
    estimate_source: str = ""
    estimate_model: str = ""
    estimate_timestamp: float | None = None
    last_input_tokens: int | None = None
    receipt_model: str = ""
    receipt_timestamp: float | None = None
    run_input_tokens: int = 0
    run_output_tokens: int = 0
    permission_grants: int = 0
    local_execution_approved: bool = False
    permission_pending: str = ""
    permission_read_roots: tuple[str, ...] = ()
    permission_write_roots: tuple[str, ...] = ()
    compaction_count: int = 0


__all__ = ["ConversationBlock", "ConversationMessage", "InteractiveMechanism", "InteractiveStatus", "ResumableSession"]
