"""Run-scoped event sequencing, tracing, and presentation isolation."""

from __future__ import annotations

import asyncio
import dataclasses
import uuid
from collections import deque
from collections.abc import Awaitable, Callable

from .events import FrontendEvent, InteractiveEvent, AuthorizationRequested


EventSink = Callable[[InteractiveEvent], Awaitable[None] | None]


class EventDispatcher:
    """Own event metadata without leaking renderer failures into Agent runs."""

    def __init__(
        self,
        sink: EventSink | None = None,
        *,
        trace_capacity: int = 200,
    ) -> None:
        self._sink = sink
        self._run_id = ""
        self._sequence = 0
        self._trace: deque[InteractiveEvent] = deque(
            maxlen=max(1, trace_capacity)
        )

    @property
    def active(self) -> bool:
        return bool(self._run_id)

    def begin_run(self) -> None:
        if self.active:
            raise RuntimeError("an interactive run is already active")
        self._run_id = uuid.uuid4().hex
        self._sequence = 0

    def end_run(self) -> None:
        self._run_id = ""

    def set_sink(self, sink: EventSink | None) -> None:
        self._sink = sink

    def trace(self, limit: int = 12) -> list[InteractiveEvent]:
        return list(self._trace)[-max(0, limit):]

    async def emit(self, event: FrontendEvent) -> None:
        if not self.active:
            return
        self._sequence += 1
        emitted = dataclasses.replace(
            event,
            run_id=self._run_id,
            sequence=self._sequence,
        )
        if not isinstance(emitted, AuthorizationRequested):
            self._trace.append(emitted)
        if self._sink is None:
            return
        try:
            result = self._sink(emitted)
            if hasattr(result, "__await__"):
                await result
        except asyncio.CancelledError:
            raise
        except Exception:
            # Presentation must not change a successful Agent run.
            return


__all__ = ["EventDispatcher", "EventSink"]
