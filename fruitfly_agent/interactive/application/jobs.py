"""Own optimization work and observation without owning Application state."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Awaitable, Callable, Mapping

from fruitfly_agent.interactive.contracts.candidates import CandidateView
from fruitfly_agent.interactive.contracts.optimization import (
    OptimizationActivityService,
    OptimizationProgress,
    OptimizationService,
)


class OptimizationJob:
    def __init__(self) -> None:
        self._task: asyncio.Task[tuple[CandidateView, ...]] | None = None
        self._service: OptimizationService | None = None
        self._progress = OptimizationProgress(0, "idle")

    def start(
        self, service: OptimizationService, manifest: Mapping[str, object], direction: str,
        *, preview_token: str,
        execute: Callable[[Callable[[], Awaitable[tuple[CandidateView, ...]]]], Awaitable[tuple[CandidateView, ...]]],
        finished: Callable[[BaseException | None], None],
    ) -> asyncio.Task[tuple[CandidateView, ...]]:
        if self._task is not None and not self._task.done():
            raise RuntimeError("optimization is already running")
        self._service = service
        sequence = self._progress.sequence + 1
        self._progress = OptimizationProgress(sequence, "running")

        async def run():
            return await execute(lambda: service.optimize(manifest, direction, preview_token=preview_token))

        task = asyncio.create_task(run())
        self._task = task

        def done(value: asyncio.Task[tuple[CandidateView, ...]]) -> None:
            error = None if value.cancelled() else value.exception()
            if self._task is not value:
                return
            self._progress = OptimizationProgress(
                sequence,
                "cancelled" if value.cancelled() else "failed" if error is not None else "completed",
                str(error) if error is not None else "", self._activity(),
            )
            finished(error)

        task.add_done_callback(done)
        return task

    def cancel(self) -> bool:
        accepted = self._service.cancel_optimization() if self._service is not None else False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            return True
        return accepted

    @property
    def progress(self) -> OptimizationProgress:
        return replace(self._progress, activity=self._activity()) if self._progress.status == "running" else self._progress

    def _activity(self):
        if isinstance(self._service, OptimizationActivityService):
            try:
                return self._service.optimization_activity()
            except Exception:
                # Observer failure must not replace the authorized work result.
                return None
        return None

    async def wait(self) -> None:
        if self._task is not None:
            try:
                await asyncio.shield(self._task)
            except (Exception, asyncio.CancelledError):
                if not self._task.done():
                    raise
