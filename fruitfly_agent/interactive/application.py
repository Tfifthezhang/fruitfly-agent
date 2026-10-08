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

from fruitfly_agent.core.data_model import AgentLoopResult

from .configuration import ConfigurationController
from .dispatch import EventSink
from .events import InteractiveEvent
from .models import ConversationMessage, InteractiveStatus, ResumableSession
from .runtime import RuntimeFactory, RuntimeHandle
from .optimization import OptimizationService, OptimizationPreview, CandidateView, OptimizationProgress, CorrectionView, OptimizationActivityService


class ApplicationState(StrEnum):
    STARTING = "starting"
    IDLE = "idle"
    RUNNING = "running"
    OPTIMIZING = "optimizing"
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
        self._pending: deque[str] = deque()
        self._worker: asyncio.Task[None] | None = None
        self._event_sink: EventSink | None = None
        self._authorization_enabled = False
        self._authorization_handler = None
        self._last_result: AgentLoopResult | None = None
        self._last_error: BaseException | None = None
        self._optimization_task: asyncio.Task[tuple[CandidateView, ...]] | None = None
        self._optimization_progress = OptimizationProgress(0, "idle")

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
        """Return compatible non-empty sessions without exposing storage details."""

        handle = self._require_handle()
        discover = getattr(self._factory, "resumable_sessions", None)
        if discover is None:
            raise RuntimeError("this runtime factory does not support session discovery")
        digest = handle.manifest.get("digest")
        if not isinstance(digest, str) or not digest:
            raise RuntimeError("the active runtime has no manifest digest")
        return discover(
            current_path=Path(handle.session.status.session_path),
            manifest_digest=digest,
        )

    def _check_submission_state(self, operation: str) -> None:
        if self._state not in {ApplicationState.IDLE, ApplicationState.RUNNING}:
            raise RuntimeError(f"cannot {operation} while application is {self._state}")

    async def submit(self, prompt: str) -> AgentLoopResult:
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

    def enqueue(self, prompt: str) -> int:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt must not be empty")
        self._check_submission_state("queue")
        self._pending.append(prompt)
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._drain_queue())
        return len(self._pending)

    def steer(self, prompt: str) -> bool:
        return self._require_handle().session.steer(prompt)

    def cancel(self) -> bool:
        had_pending = bool(self._pending)
        self._pending.clear()
        if self._state == ApplicationState.OPTIMIZING:
            service = self._optimization_service()
            accepted = service.cancel_optimization()
            if self._optimization_task is not None:
                self._optimization_task.cancel()
                return True
            return accepted
        return self._require_handle().session.cancel() or had_pending

    def _optimization_service(self) -> OptimizationService:
        service = self._require_handle().optimization
        if service is None:
            raise RuntimeError("this runtime has no optimization service")
        return service

    @property
    def task_packs_available(self) -> bool:
        from .optimization import TaskPackService
        return self._handle is not None and isinstance(self._handle.optimization, TaskPackService)

    def _task_pack_service(self):
        from .optimization import TaskPackService
        service = self._optimization_service()
        if not isinstance(service, TaskPackService):
            raise RuntimeError("task package service is unavailable")
        return service

    def task_packs(self):
        return self._task_pack_service().task_packs()

    def task_pack_holdout(self, pack_id):
        return self._task_pack_service().task_pack_holdout(pack_id)

    def correction_tasks(self):
        from fruitfly_agent.core.data_model import UserMessage, AssistantMessage, TextBlock
        rows: list[CorrectionView] = []
        current, output, tools = None, "", False
        def finish():
            if current is not None and output.strip():
                content = current.message.content
                text = content if isinstance(content, str) else "".join(
                    block.text for block in content if isinstance(block, TextBlock)
                )
                rows.append(CorrectionView(current.id, text, output, tools or bool(rows)))
        for item in self._require_handle().session.canonical_items():
            message = item.message
            if isinstance(message, UserMessage):
                finish()
                current, output, tools = item, "", False
            elif isinstance(message, AssistantMessage) and current is not None:
                tools = tools or bool(message.tool_calls)
                if message.stop_reason in {"stop", "length"}:
                    output = message.text
        finish()
        return tuple(reversed(rows[-20:]))

    def save_training_task(self, task_id, pack_id, input, expected, **options):
        if self._state != ApplicationState.IDLE or self._pending:
            raise RuntimeError("finish active work before saving a task")
        task = next((t for t in self.correction_tasks() if t.task_id == task_id), None)
        if task is None:
            raise ValueError("completed task unavailable; select it again")
        import hashlib
        source = {"session": self.status.session_path, "message_id": task_id,
                  "parent_manifest": str(self.runtime_manifest.get("digest", "")),
                  "original_output_hash": "sha256:" + hashlib.sha256(task.output.encode()).hexdigest()}
        return self._task_pack_service().save_training_task(pack_id, input, expected, source=source, **options)

    def optimization_preview(self, *, pack_id=None, direction="") -> OptimizationPreview:
        if self._state != ApplicationState.IDLE or self._pending:
            raise RuntimeError("finish active work before starting optimization")
        return self._optimization_service().optimization_preview(self.runtime_manifest, pack_id=pack_id, direction=direction)

    def start_optimization(self, direction: str, *, preview_token="") -> asyncio.Task[tuple[CandidateView, ...]]:
        """Own confirmed work while allowing the frontend to continue reading input."""
        if self._state != ApplicationState.IDLE or self._pending:
            raise RuntimeError("finish active work before starting optimization")
        service = self._optimization_service()
        manifest = self.runtime_manifest
        self._state = ApplicationState.OPTIMIZING
        self._last_error = None
        self._optimization_progress = OptimizationProgress(self._optimization_progress.sequence + 1, "running")

        async def execute():
            try:
                async with self._submission_lock:
                    return await service.optimize(manifest, direction, preview_token=preview_token)
            finally:
                if self._state == ApplicationState.OPTIMIZING:
                    self._state = ApplicationState.IDLE

        task = asyncio.create_task(execute())
        self._optimization_task = task

        def finished(value):
            activity = self._optimization_activity()
            if self._state == ApplicationState.OPTIMIZING:
                self._state = ApplicationState.IDLE
            if value.cancelled():
                self._optimization_progress = OptimizationProgress(self._optimization_progress.sequence, "cancelled", activity=activity)
            else:
                self._last_error = value.exception()
                self._optimization_progress = OptimizationProgress(
                    self._optimization_progress.sequence,
                    "failed" if self._last_error is not None else "completed",
                    str(self._last_error) if self._last_error is not None else "",
                    activity=activity,
                )

        task.add_done_callback(finished)
        return task

    async def optimize(self, direction: str, *, preview_token="") -> tuple[CandidateView, ...]:
        return await self.start_optimization(direction, preview_token=preview_token)

    @property
    def optimization_progress(self) -> OptimizationProgress:
        progress = self._optimization_progress
        return replace(progress, activity=self._optimization_activity()) if progress.status == "running" else progress

    def _optimization_activity(self):
        service = self._handle.optimization if self._handle is not None else None
        if isinstance(service, OptimizationActivityService):
            try:
                return service.optimization_activity()
            except Exception:
                # A presentation observer must never stop or replace authorized work.
                return None
        return None

    async def wait_for_optimization(self) -> None:
        task = self._optimization_task
        if task is not None:
            try:
                await asyncio.shield(task)
            except (Exception, asyncio.CancelledError):
                if not task.done():
                    raise

    def candidates(self) -> tuple[CandidateView, ...]:
        service = self._require_handle().optimization
        return () if service is None else service.candidates()

    def candidate_notice(self) -> tuple[str, ...]:
        service = self._require_handle().optimization
        return () if service is None else service.candidate_notice()

    def acknowledge_candidate_notice(self, candidate_ids: tuple[str, ...]) -> None:
        self._optimization_service().acknowledge_candidate_notice(candidate_ids)

    def candidate_detail(self, candidate_id: str) -> tuple[CandidateView, str]:
        return self._optimization_service().candidate_detail(candidate_id)

    def candidate_action(self, candidate_id: str, action: str) -> CandidateView:
        if self._state != ApplicationState.IDLE or self._pending:
            raise RuntimeError("finish active work before reviewing candidates")
        return self._optimization_service().candidate_action(self.runtime_manifest, candidate_id, action)

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
            raise ValueError("candidate no longer exists")
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
                await self.wait_for_optimization()
                await self.wait_until_idle()
                async with self._submission_lock:
                    pass
        except TimeoutError as exc:
            error = RuntimeError("active work did not stop before the shutdown deadline; runtime retained")
            self._last_error = error
            raise error from exc

    async def rebuild(self) -> None:
        """Apply saved configuration by replacing the complete runtime/session."""

        if self._handle is None:
            raise RuntimeError("application is not started")
        if self._state == ApplicationState.OPTIMIZING:
            raise RuntimeError("cancel or finish optimization before rebuilding")
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
                candidate = await self._factory.open(
                    resume=False, session_path=self._factory.new_session_path(),
                )
                await self._prepare_handle(candidate)
            except BaseException:
                try:
                    if candidate is not None:
                        await candidate.close()
                finally:
                    self._state = ApplicationState.IDLE
                raise
            self._handle = candidate
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
        if self._state == ApplicationState.OPTIMIZING:
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
