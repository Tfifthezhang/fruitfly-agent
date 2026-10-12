"""Adapt optional embedding capabilities once at the terminal boundary."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from fruitfly_agent.interactive.contracts.events import EventSink
from fruitfly_agent.interactive.contracts.models import InteractiveStatus
from fruitfly_agent.interactive.contracts.optimization import OptimizationClient, OptimizationProgress
from fruitfly_agent.interactive.contracts.candidates import CandidateClient, CandidateActivationClient
from fruitfly_agent.interactive.contracts.task_packs import TaskPackClient


class TerminalSession(Protocol):
    @property
    def status(self) -> InteractiveStatus: ...
    @property
    def running(self) -> bool: ...
    def set_event_sink(self, sink: EventSink | None) -> None: ...
    def steer(self, prompt: str) -> bool: ...
    def cancel(self) -> bool: ...
    async def submit(self, prompt: str): ...


@dataclass(frozen=True)
class TerminalBindings:
    """Explicit optional operations; readers follow runtime replacement."""
    cancel: Callable[[], bool]
    enqueue: Callable[[str], int] | None
    wait: Callable[[], Awaitable[None]] | None
    rebuild: Callable[[], Awaitable[None]] | None
    resume: Callable[..., Awaitable[None]] | None
    discover: Callable | None
    conversation: Callable | None
    configuration: Callable
    busy: Callable[[], bool]
    authorization: Callable
    enable_authorization: Callable | None
    progress: Callable
    candidate_notice: Callable | None
    acknowledge_notice: Callable | None

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
            busy=lambda: bool(getattr(session, "running", False) or getattr(session, "pending_count", 0)),
            authorization=lambda: getattr(session, "authorization", None),
            enable_authorization=getattr(session, "enable_authorization", None),
            progress=lambda: getattr(session, "optimization_progress", None),
            candidate_notice=getattr(session, "candidate_notice", None),
            acknowledge_notice=getattr(session, "acknowledge_candidate_notice", None),
        )


@dataclass(frozen=True)
class ImprovementClients:
    """Menus can compose distinct feature clients without an Application object."""
    search: OptimizationClient | None = None
    candidates: CandidateClient | None = None
    materials: TaskPackClient | None = None
    activation: CandidateActivationClient | None = None
    progress: Callable[[], OptimizationProgress | None] = lambda: None

    @classmethod
    def from_session(cls, session: Any) -> ImprovementClients:
        return cls(
            search=session if isinstance(session, OptimizationClient) else None,
            candidates=session if isinstance(session, CandidateClient) else None,
            materials=session if isinstance(session, TaskPackClient) else None,
            activation=session if isinstance(session, CandidateActivationClient) else None,
            progress=lambda: getattr(session, "optimization_progress", None),
        )

    @property
    def available(self) -> bool:
        return any(client is not None for client in (self.search, self.candidates, self.materials))
