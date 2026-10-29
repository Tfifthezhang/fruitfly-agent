"""Adapt optional embedding capabilities once at the terminal boundary."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol
from fruitfly_agent.interactive.contracts.inputs import ImageAttachment, UserContent

from fruitfly_agent.interactive.contracts.events import EventSink
from fruitfly_agent.interactive.contracts.models import InteractiveStatus
from fruitfly_agent.interactive.contracts.improvement import ImprovementClient, ImprovementProgress, ComponentImprovementClient
from fruitfly_agent.interactive.contracts.candidates import CandidateClient, CandidateActivationClient
from fruitfly_agent.interactive.contracts.task_packs import TaskPackClient
from fruitfly_agent.interactive.contracts.experience import ExperienceReviewClient


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
    progress: Callable
    candidate_notice: Callable | None
    acknowledge_notice: Callable | None
    apply_configuration: Callable[[], Awaitable[None]] | None = None
    load_attachment: Callable[[str], ImageAttachment] | None = None
    validate_input: Callable[[UserContent], UserContent] | None = None

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
            progress=lambda: getattr(session, "improvement_progress", None),
            candidate_notice=getattr(session, "candidate_notice", None),
            acknowledge_notice=getattr(session, "acknowledge_candidate_notice", None),
            apply_configuration=getattr(session, "apply_configuration", None),
            load_attachment=(getattr(session, 'load_attachment', None)
                             if getattr(session, 'attachments_available', True) else None),
            validate_input=getattr(session, 'validate_input', None),
        )


@dataclass(frozen=True)
class ImprovementClients:
    """Menus can compose distinct feature clients without an Application object."""
    search: ImprovementClient | None = None
    candidates: CandidateClient | None = None
    materials: TaskPackClient | None = None
    activation: CandidateActivationClient | None = None
    progress: Callable[[], ImprovementProgress | None] = lambda: None
    history: Callable = lambda: ()
    cancel: Callable[[], bool] = lambda: False
    history_logs: Callable | None = None
    wait: Callable | None = None
    workflow: ComponentImprovementClient | None = None
    experience: ExperienceReviewClient | None = None

    @classmethod
    def from_session(cls, session: Any) -> ImprovementClients:
        return cls(
            search=session if isinstance(session, ImprovementClient) else None,
            candidates=session if isinstance(session, CandidateClient) else None,
            materials=session if isinstance(session, TaskPackClient) else None,
            activation=session if isinstance(session, CandidateActivationClient) else None,
            progress=lambda: getattr(session, "improvement_progress", None),
            history=getattr(session, 'improvement_history', lambda: ()),
            cancel=getattr(session, 'cancel', lambda: False),
            history_logs=getattr(session, 'improvement_run_logs', None),
            wait=getattr(session, 'wait_for_improvement', None),
            workflow=session if isinstance(session, ComponentImprovementClient) else None,
            experience=session if isinstance(session, ExperienceReviewClient) else None,
        )

    @property
    def available(self) -> bool:
        return any(client is not None for client in (self.workflow, self.search, self.candidates, self.materials))
