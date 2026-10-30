"""Frontend-neutral application lifecycle above one or more runtime sessions."""

from __future__ import annotations

import asyncio
from collections import deque
import copy
import math
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from fruitfly_agent.core.data_model import AgentLoopResult, ImageBlock
from fruitfly_agent.core.data_model.media import UserContent, normalize_input

from fruitfly_agent.interactive.contracts.configuration import ConfigurationController
from fruitfly_agent.interactive.contracts.events import EventSink
from fruitfly_agent.interactive.contracts.events import InteractiveEvent
from fruitfly_agent.interactive.contracts.models import (
    ConversationMessage,
    InteractiveStatus,
    ResumableSession,
)
from fruitfly_agent.interactive.contracts.runtime import RuntimeFactory, RuntimeHandle
from fruitfly_agent.interactive.contracts.improvement import (
    ImprovementService,
    ImprovementPreview,
    ImprovementProgress,
    ComponentImprovementClient,
)
from fruitfly_agent.interactive.contracts.candidates import CandidateView, CandidateService
from fruitfly_agent.interactive.contracts.task_packs import TaskPackService
from fruitfly_agent.interactive.contracts.experience import ExperienceReviewClient
from fruitfly_agent.interactive.application.jobs import ImprovementJob
from fruitfly_agent.interactive.session.materials import TaskMaterials


class ApplicationState(StrEnum):
    STARTING = "starting"
    IDLE = "idle"
    RUNNING = "running"
    IMPROVING = "improving"
    REBUILDING = "rebuilding"
    RESUMING = "resuming"
    CLOSING = "closing"
    CLOSED = "closed"


class AgentApplication:
    """Own runtime rebuilds and serialize user work independently of a frontend."""

    def __init__(self, factory: RuntimeFactory, *, shutdown_timeout: float = 10.0) -> None:
        if isinstance(shutdown_timeout, bool) or not math.isfinite(shutdown_timeout) or shutdown_timeout <= 0:
            raise ValueError("shutdown_timeout must be finite and positive")
        self._shutdown_timeout = shutdown_timeout
        self._factory = factory
        self._handle: RuntimeHandle | None = None
        self._state = ApplicationState.CLOSED
        self._submission_lock = asyncio.Lock()
        self._pending: deque[UserContent] = deque()
        self._worker: asyncio.Task[None] | None = None
        self._event_sink: EventSink | None = None
        self._authorization_enabled = False
        self._authorization_handler = None
        self._last_result: AgentLoopResult | None = None
        self._last_error: BaseException | None = None
        self._improvement_job = ImprovementJob()
        self._materials = TaskMaterials(
            service=self._task_pack_service,
            items=lambda: self._require_handle().session.canonical_items(),
            session_path=lambda: self.status.session_path,
            manifest=lambda: self.runtime_manifest,
        )

    @property
    def state(self) -> ApplicationState:
        return self._state

    @property
    def running(self) -> bool:
        return self._state == ApplicationState.RUNNING

    @property
    def configuration(self) -> ConfigurationController:
        return self._factory.configuration

    @property
    def runtime_manifest(self) -> Mapping[str, Any]:
        """Return a read-only snapshot suitable for an external consumer."""

        return copy.deepcopy(dict(self._require_handle().manifest))

    @property
    def status(self) -> InteractiveStatus:
        prompt = self._require_handle().manifest.get("base_prompt", {})
        return replace(
            self._require_handle().session.status,
            application_state=self._state.value,
            pending_count=len(self._pending),
            improvement_available=isinstance(self._require_handle().improvement, ComponentImprovementClient),
            prompt_label=str(prompt.get("label", "")),
            prompt_hash=str(prompt.get("content_hash", "")),
            permission_grants=self.authorization.status()['grants'] if self.authorization is not None else 0,
            local_execution_approved=self.authorization.status()['local_execution'] if self.authorization is not None else False,
            permission_pending=self.authorization.status()['pending'] if self.authorization is not None else '',
            permission_read_roots=tuple(self._require_handle().manifest.get('permissions', {}).get('read_roots', ())),
            permission_write_roots=tuple(self._require_handle().manifest.get('permissions', {}).get('write_roots', ())),
        )

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def last_result(self) -> AgentLoopResult | None:
        return self._last_result

    @property
    def last_error(self) -> BaseException | None:
        return self._last_error

    async def start(
        self,
        *,
        resume: bool = False,
        session_path: Path | None = None,
    ) -> None:
        if self._handle is not None:
            raise RuntimeError("application is already started")
        self._state = ApplicationState.STARTING
        handle: RuntimeHandle | None = None
        try:
            handle = await self._factory.open(
                resume=resume,
                session_path=session_path,
            )
            await handle.start()
            if handle.activate_callback is not None:
                handle.activate_callback()
        except BaseException:
            try:
                if handle is not None:
                    await handle.close()
            finally:
                self._state = ApplicationState.CLOSED
            raise
        self._handle = handle
        handle.session.set_event_sink(self._event_sink)
        if handle.authorization is not None:
            handle.authorization.available = self._authorization_enabled
            handle.authorization.handler = self._authorization_handler
        self._state = ApplicationState.IDLE

    @property
    def authorization(self):
        return self._handle.authorization if self._handle is not None else None

    def enable_authorization(self, enabled=True):
        self._authorization_enabled = bool(enabled)
        if self.authorization is not None:
            self.authorization.available = bool(enabled)
            if not enabled:
                self.authorization.clear()

    def set_authorization_handler(self, handler):
        self._authorization_handler = handler
        if self.authorization is not None:
            self.authorization.handler = handler

    def clear_authorizations(self):
        if self.authorization is not None:
            self.authorization.clear()

    def set_event_sink(self, sink: EventSink | None) -> None:
        self._event_sink = sink
        if self._handle is not None:
            self._handle.session.set_event_sink(sink)

    def trace(self, limit: int = 12) -> list[InteractiveEvent]:
        return self._require_handle().session.trace(limit)

    def conversation(self) -> tuple[ConversationMessage, ...]:
        """Return the active session's immutable canonical conversation view."""
        return self._require_handle().session.conversation()

    def resumable_sessions(self) -> tuple[ResumableSession, ...]:
        """Return persisted sessions and availability without transcript contents."""

        handle = self._require_handle()
        discover = getattr(self._factory, "resumable_sessions", None)
        if discover is None:
            raise RuntimeError("this runtime factory does not support session discovery")
        return discover(
            current_path=Path(handle.session.status.session_path),
        )

    def _check_submission_state(self, operation: str) -> None:
        if self._state not in {ApplicationState.IDLE, ApplicationState.RUNNING}:
            raise RuntimeError(f"cannot {operation} while application is {self._state}")

    def validate_input(self, prompt: UserContent) -> UserContent:
        content = normalize_input(prompt)
        validate = getattr(self._require_handle().session, 'validate_input', None)
        if callable(validate):
            validate(content)
        return content

    @property
    def attachments_available(self) -> bool:
        session = self._require_handle().session
        return bool(getattr(session, 'attachments_available', callable(getattr(session, 'load_attachment', None))))

    def load_attachment(self, path: str) -> ImageBlock:
        return self._require_handle().session.load_attachment(path)

    async def submit(self, prompt: UserContent) -> AgentLoopResult:
        prompt = self.validate_input(prompt)
        async with self._submission_lock:
            self._check_submission_state("submit")
            self._state = ApplicationState.RUNNING
            try:
                result = await self._require_handle().session.submit(prompt)
                self._last_result = result
                return result
            finally:
                if self._state == ApplicationState.RUNNING:
                    self._state = ApplicationState.IDLE

    def enqueue(self, prompt: UserContent) -> int:
        prompt = self.validate_input(prompt)
        self._check_submission_state("queue")
        self._pending.append(prompt)
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._drain_queue())
        return len(self._pending)

    def steer(self, prompt: UserContent) -> bool:
        return self._require_handle().session.steer(prompt)

    def cancel(self) -> bool:
        had_pending = bool(self._pending)
        self._pending.clear()
        if self._state == ApplicationState.IMPROVING:
            return self._improvement_job.cancel()
        return self._require_handle().session.cancel() or had_pending

    def _improvement_service(self) -> ImprovementService:
        service = self._require_handle().improvement
        if service is None:
            raise RuntimeError("this runtime has no improvement service")
        return service

    @property
    def task_packs_available(self) -> bool:
        return self._handle is not None and self._handle.task_packs is not None

    def _task_pack_service(self) -> TaskPackService:
        service = self._require_handle().task_packs
        if service is None:
            raise RuntimeError("task package service is unavailable")
        return service

    def task_packs(self):
        return self._task_pack_service().task_packs()

    def task_packs_for_target(self, target_id):
        service = self._task_pack_service()
        query = getattr(service, 'task_packs_for_target', None)
        return query(target_id) if query is not None else service.task_packs()

    def task_pack_holdout(self, pack_id):
        return self._task_pack_service().task_pack_holdout(pack_id)

    def correction_tasks(self):
        return self._materials.corrections()

    def save_training_task(self, task_id, pack_id, input, expected, **options):
        if self._state != ApplicationState.IDLE or self._pending:
            raise RuntimeError("finish active work before saving a task")
        return self._materials.save(task_id, pack_id, input, expected, **options)

    def workflow_configuration(self):
        service = self._improvement_service()
        return service.workflow_configuration() if isinstance(service, ComponentImprovementClient) else None

    def workflow_preview(self, request):
        if self._state != ApplicationState.IDLE or self._pending:
            raise RuntimeError('finish active work before preparing improvement')
        service = self._improvement_service()
        if not isinstance(service, ComponentImprovementClient):
            raise RuntimeError('component improvement is unavailable')
        return service.workflow_preview(request)

    def improvement_targets(self):
        configuration = self.workflow_configuration()
        return configuration.components if configuration is not None else ()

    def improvement_history(self):
        query = getattr(self._improvement_service(), 'improvement_history', None)
        return query() if query is not None else ()

    def improvement_run_logs(self, run_id):
        query = getattr(self._improvement_service(), 'improvement_run_logs', None)
        return query(run_id) if query is not None else 'This host does not provide search logs.'

    def pending_experience(self):
        service = self._improvement_service()
        return service.pending_experience() if isinstance(service, ExperienceReviewClient) else ()

    def experience_action(self, job_id, action):
        if self._state != ApplicationState.IDLE or self._pending:
            raise RuntimeError('finish active work before reviewing experience')
        service = self._improvement_service()
        if not isinstance(service, ExperienceReviewClient):
            raise RuntimeError('experience review is unavailable')
        return service.experience_action(job_id, action)

    def start_improvement(self, direction: str, *, preview_token="") -> asyncio.Task[tuple[CandidateView, ...]]:
        """Own confirmed work while allowing the frontend to continue reading input."""
        if self._state != ApplicationState.IDLE or self._pending:
            raise RuntimeError("finish active work before starting improvement")
        service = self._improvement_service()
        manifest = self.runtime_manifest
        submitted = getattr(service, 'improvement_submitted', None)
        if submitted is not None:
            preview_token = submitted(manifest, direction, preview_token=preview_token)
        self._state = ApplicationState.IMPROVING
        self._last_error = None
        async def execute(operation):
            try:
                async with self._submission_lock:
                    return await operation()
            finally:
                if self._state == ApplicationState.IMPROVING:
                    self._state = ApplicationState.IDLE

        def finished(error):
            if self._state == ApplicationState.IMPROVING:
                self._state = ApplicationState.IDLE
            self._last_error = error
            completed = getattr(service, 'improvement_finished', None)
            if completed is not None:
                try:
                    completed(preview_token, self._improvement_job.progress.status, str(error) if error else '')
                except Exception as exc:
                    self._last_error = exc

        return self._improvement_job.start(
            service, manifest, direction, preview_token=preview_token,
            execute=execute, finished=finished,
        )

    async def improve(self, direction: str, *, preview_token="") -> tuple[CandidateView, ...]:
        return await self.start_improvement(direction, preview_token=preview_token)

    @property
    def improvement_progress(self) -> ImprovementProgress:
        return self._improvement_job.progress

    async def wait_for_improvement(self) -> None:
        await self._improvement_job.wait()

    def _candidate_service(self) -> CandidateService:
        service = self._require_handle().candidates
        if service is None:
            raise RuntimeError("this runtime has no candidate service")
        return service

    def candidates(self) -> tuple[CandidateView, ...]:
        service = self._require_handle().candidates
        return () if service is None else service.candidates()

    def candidate_notice(self) -> tuple[str, ...]:
        service = self._require_handle().candidates
        return () if service is None else service.candidate_notice()

    def acknowledge_candidate_notice(self, candidate_ids: tuple[str, ...]) -> None:
        self._candidate_service().acknowledge_candidate_notice(candidate_ids)

    def candidate_detail(self, candidate_id: str) -> tuple[CandidateView, str]:
        return self._candidate_service().candidate_detail(candidate_id)

    def candidate_action(self, candidate_id: str, action: str) -> CandidateView:
        if self._state != ApplicationState.IDLE or self._pending:
            raise RuntimeError("finish active work before reviewing candidates")
        return self._candidate_service().candidate_action(self.runtime_manifest, candidate_id, action)

    async def adopt_candidate(self, candidate_id: str) -> CandidateView:
        """Prepare and activate a candidate as a fresh session atomically at the host boundary."""
        if self._state != ApplicationState.IDLE or self._pending:
            raise RuntimeError("finish active work before activating a candidate")
        if self._handle is None:
            raise RuntimeError("application is not started")
        service = self._require_handle().candidate_activation
        if service is None:
            raise RuntimeError("candidate activation is unavailable")
        candidate_view = next((item for item in self.candidates()
                               if item.candidate_id == candidate_id), None)
        if candidate_view is None:
            # History may reference a retained candidate outside the latest inbox.
            # Host preparation still validates scope, parent, binding and artifact.
            candidate_view, _ = self.candidate_detail(candidate_id)
        previous = self._handle
        expected = self.runtime_manifest.get("digest")
        self._state = ApplicationState.REBUILDING
        candidate = None
        try:
            async with self._submission_lock:
                if self._handle is not previous or self.runtime_manifest.get("digest") != expected:
                    raise RuntimeError("active runtime changed before candidate activation")
                candidate = await service.prepare_candidate(self.runtime_manifest, candidate_id)
                await self._prepare_handle(candidate)
                self._handle = candidate
        except BaseException:
            try:
                if candidate is not None:
                    await candidate.close()
            finally:
                self._state = ApplicationState.IDLE
            raise
        self._last_result = None
        self._last_error = None
        self._state = ApplicationState.IDLE
        await self._close_previous(previous)
        return replace(candidate_view, status="adopted")

    async def wait_until_idle(self) -> None:
        worker = self._worker
        if worker is not None:
            await asyncio.shield(worker)

    async def _quiesce(self) -> None:
        """Bound retirement waits without closing a still-active handle."""
        try:
            async with asyncio.timeout(self._shutdown_timeout):
                await self.wait_for_improvement()
                await self.wait_until_idle()
                async with self._submission_lock:
                    pass
        except TimeoutError as exc:
            error = RuntimeError("active work did not stop before the shutdown deadline; runtime retained")
            self._last_error = error
            raise error from exc

    async def apply_configuration(self) -> None:
        """Apply the host's draft through assembly without changing conversation identity."""
        if self._handle is None:
            raise RuntimeError("application is not started")
        if self._state != ApplicationState.IDLE or self._pending:
            raise RuntimeError("finish or cancel active work before applying configuration")
        async with self._submission_lock:
            if self._state != ApplicationState.IDLE or self._pending:
                raise RuntimeError("finish or cancel active work before applying configuration")
            previous = self._handle
            self._state = ApplicationState.REBUILDING
            candidate: RuntimeHandle | None = None
            try:
                candidate = await self._factory.prepare_configuration(
                    session_path=Path(previous.session.status.session_path))
                await self._prepare_handle(candidate)
            except BaseException:
                try:
                    if candidate is not None:
                        await candidate.close()
                finally:
                    self._state = ApplicationState.IDLE
                raise
            self._handle = candidate
            self._last_result = None
            self._last_error = None
            await self._close_previous(previous)
            self._state = ApplicationState.IDLE

    async def replace_factory(self, factory: RuntimeFactory) -> None:
        """Replace an idle host using the same checked runtime activation boundary."""
        if self._state != ApplicationState.IDLE or self._pending:
            raise RuntimeError('finish active work before replacing the runtime host')
        expected = self.runtime_manifest['digest']
        path = Path(self._require_handle().session.status.session_path)
        candidate = await factory.open(resume=True, session_path=path)
        await self.activate_runtime(candidate, expected_manifest_digest=expected)
        self._factory = factory

    async def rebuild(self, *, preserve_session: bool = False) -> None:
        """Replace the runtime; recover its Session only when explicitly selected."""

        if self._handle is None:
            raise RuntimeError("application is not started")
        if self._state == ApplicationState.IMPROVING:
            raise RuntimeError("cancel or finish improvement before rebuilding")
        self._state = ApplicationState.REBUILDING
        self._pending.clear()
        self.cancel()
        try:
            await self._quiesce()
        except BaseException:
            self._state = ApplicationState.RUNNING if self._require_handle().session.running else ApplicationState.IDLE
            raise
        # Queue workers use submit(), but an embedding host may call submit()
        # directly.  Serialize replacement with both paths so no live run can
        # retain resources from the handle being closed.
        async with self._submission_lock:
            previous = self._handle
            candidate: RuntimeHandle | None = None
            try:
                self._factory.reload_configuration()
                candidate = await self._factory.open(resume=preserve_session, session_path=(
                    Path(previous.session.status.session_path) if preserve_session
                    else self._factory.new_session_path()))
                await self._prepare_handle(candidate)
            except BaseException:
                try:
                    if candidate is not None:
                        await candidate.close()
                finally:
                    self._state = ApplicationState.IDLE
                raise
            self._handle = candidate
            self._last_result = None
            self._last_error = None
            await self._close_previous(previous)
            self._state = ApplicationState.IDLE

    async def resume(self, session_path: str | Path) -> None:
        """Replace an idle runtime with a successfully restored candidate."""

        if self._handle is None:
            raise RuntimeError("application is not started")
        if self._state != ApplicationState.IDLE or self._pending:
            raise RuntimeError("finish or cancel active work before resuming a session")
        target = Path(session_path)
        current = Path(self._handle.session.status.session_path)
        if target.resolve() == current.resolve():
            raise ValueError("the requested session is already active")

        async with self._submission_lock:
            if self._state != ApplicationState.IDLE or self._pending:
                raise RuntimeError(
                    "finish or cancel active work before resuming a session"
                )
            previous = self._handle
            self._state = ApplicationState.RESUMING
            candidate: RuntimeHandle | None = None
            try:
                candidate = await self._factory.open(
                    resume=True,
                    session_path=target,
                )
                await self._prepare_handle(candidate)
            except BaseException as exc:
                if candidate is not None:
                    try:
                        await candidate.close()
                    except BaseException:
                        pass
                self._state = ApplicationState.IDLE
                if isinstance(exc, Exception):
                    raise RuntimeError(f"could not restore session: {exc}") from exc
                raise

            self._handle = candidate
            self._last_result = None
            self._last_error = None
            self._state = ApplicationState.IDLE
            await self._close_previous(previous)

    async def activate_runtime(self, candidate: RuntimeHandle, *, expected_manifest_digest: str) -> None:
        """Consume a prepared handle; failure closes it and retains the incumbent.

        The injected host must bind/verify candidate content before preparing it.
        This method owns startup and the active-version conditional switch.
        """
        if candidate is self._handle:
            raise ValueError("candidate must be a distinct prepared handle")
        switching = False
        try:
            if self._state != ApplicationState.IDLE or self._pending:
                raise RuntimeError("finish active work before activating a candidate")
            async with self._submission_lock:
                if self._state != ApplicationState.IDLE or self._pending or self.runtime_manifest.get("digest") != expected_manifest_digest:
                    raise ValueError("active runtime changed before candidate activation")
                previous = self._require_handle()
                self._state = ApplicationState.REBUILDING
                switching = True
                await self._prepare_handle(candidate)
                self._handle = candidate
        except BaseException:
            try:
                await candidate.close()
            finally:
                if switching:
                    self._state = ApplicationState.IDLE
            raise
        await self._close_previous(previous)
        self._state = ApplicationState.IDLE

    async def _prepare_handle(self, handle: RuntimeHandle) -> None:
        """Start and bind a replacement before committing it as active."""
        await handle.start()
        handle.session.set_event_sink(self._event_sink)
        if handle.authorization is not None:
            handle.authorization.available = self._authorization_enabled
            handle.authorization.handler = self._authorization_handler
        if handle.activate_callback is not None:
            handle.activate_callback()

    async def _close_previous(self, handle: RuntimeHandle) -> None:
        """Keep a successful switch active when retiring the old runtime fails."""
        try:
            await handle.close()
        except BaseException as exc:
            self._last_error = exc

    async def close(self) -> None:
        if self._state == ApplicationState.CLOSED and self._handle is None:
            return
        if self._state == ApplicationState.IMPROVING:
            self.cancel()
        self._state = ApplicationState.CLOSING
        self._pending.clear()
        if self._handle is not None:
            self._handle.session.cancel()
        await self._quiesce()
        async with self._submission_lock:
            handle, self._handle = self._handle, None
            try:
                if handle is not None:
                    await handle.close()
            finally:
                self._state = ApplicationState.CLOSED

    async def health(self) -> dict[str, Any]:
        return await self._require_handle().health()

    async def _drain_queue(self) -> None:
        self._last_error = None
        while self._pending:
            prompt = self._pending.popleft()
            try:
                await self.submit(prompt)
            except BaseException as exc:
                self._last_error = exc
                self._pending.clear()
                return

    def _require_handle(self) -> RuntimeHandle:
        if self._handle is None:
            raise RuntimeError("application is not started")
        return self._handle


__all__ = [
    "AgentApplication",
    "ApplicationState",
    "RuntimeFactory",
    "RuntimeHandle",
]
