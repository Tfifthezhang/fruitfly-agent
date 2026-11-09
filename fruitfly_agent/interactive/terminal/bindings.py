"""Adapt optional embedding capabilities once at the terminal boundary."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol
from fruitfly_agent.interactive.contracts.inputs import ImageAttachment, UserContent

from fruitfly_agent.interactive.contracts.events import EventSink
from fruitfly_agent.interactive.contracts.models import InteractiveStatus


class TerminalSession(Protocol):
    @property
    def status(self) -> InteractiveStatus: ...
    @property
    def running(self) -> bool: ...
    def set_event_sink(self, sink: EventSink | None) -> None: ...
    def steer(self, prompt: UserContent) -> bool: ...
    def cancel(self) -> bool: ...
    async def submit(self, prompt: UserContent): ...


@dataclass(frozen=True)
class TerminalBindings:
    """Explicit optional operations; readers follow runtime replacement."""
    cancel: Callable[[], bool]
    enqueue: Callable[[UserContent], int] | None
    wait: Callable[[], Awaitable[None]] | None
    rebuild: Callable[[], Awaitable[None]] | None
    resume: Callable[..., Awaitable[None]] | None
    discover: Callable | None
    conversation: Callable | None
    configuration: Callable
    busy: Callable[[], bool]
    authorization: Callable
    enable_authorization: Callable | None
    apply_configuration: Callable[[], Awaitable[None]] | None = None
    load_attachment: Callable[[str], ImageAttachment] | None = None
    clipboard_image: Callable[[], ImageAttachment | None] | None = None
    validate_input: Callable[[UserContent], UserContent] | None = None
    operations: Callable | None = None
    retained_state: Callable | None = None
    retained_document: Callable | None = None
    retained_action: Callable | None = None

    @classmethod
    def from_session(cls, session: Any) -> TerminalBindings:
        # Compatibility discovery is confined to assembly, not command flows.
        return cls(
            cancel=getattr(session, "cancel", lambda: False),
            enqueue=getattr(session, "enqueue", None),
            wait=getattr(session, "wait_until_idle", None),
            rebuild=getattr(session, "rebuild", None),
            resume=getattr(session, "resume", None),
            discover=getattr(session, "resumable_sessions", None),
            conversation=getattr(session, "conversation", None),
            configuration=lambda: getattr(session, "configuration", None),
            busy=lambda: bool(getattr(session, "running", False) or getattr(session, "pending_count", 0)
                              or getattr(getattr(session, "status", None), "application_state", "idle") != "idle"),
            authorization=lambda: getattr(session, "authorization", None),
            enable_authorization=getattr(session, "enable_authorization", None),
            apply_configuration=getattr(session, "apply_configuration", None),
            load_attachment=(getattr(session, 'load_attachment', None)
                             if getattr(session, 'attachments_available', True) else None),
            validate_input=getattr(session, 'validate_input', None),
            operations=lambda: getattr(session, 'operations', None),
            retained_state=getattr(session, 'retained_state', None),
            retained_document=getattr(session, 'retained_document', None),
            retained_action=getattr(session, 'retained_action', None),
        )

