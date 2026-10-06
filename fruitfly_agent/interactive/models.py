"""Renderer-neutral read models exposed by the interactive application."""

from __future__ import annotations

from dataclasses import dataclass


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


__all__ = ["InteractiveMechanism", "InteractiveStatus", "ResumableSession"]
