"""Task-local correlation and passive spans, independent of execution policy."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
import logging
import time
from typing import Iterator
from uuid import uuid4

from .models import FailureInfo, ObservationSink, OperationEvent
from .validation import observed_identifier

logger = logging.getLogger(__name__)
_CLOCK = uuid4().hex


@dataclass(frozen=True)
class ObservationContext:
    sink: ObservationSink | None = None
    run_id: str = ''
    parent_operation_id: str = ''
    component_id: str = ''
    model_role: str = ''
    request_id: str = ''
    tool_call_id: str = ''
    tool_name: str = ''


_current: ContextVar[ObservationContext] = ContextVar('fruitfly_observation', default=ObservationContext())


def current_observation() -> ObservationContext:
    return _current.get()


@contextmanager
def bind_observation(context: ObservationContext) -> Iterator[None]:
    token = _current.set(context)
    try:
        yield
    finally:
        _current.reset(token)


class OperationScope:
    def __init__(self, event: OperationEvent, sink: ObservationSink | None) -> None:
        self.event = event
        self.sink = sink
        self.state = 'succeeded'
        self.failure: FailureInfo | None = None
        self.finished = False

    def fail(self, failure: FailureInfo, *, state: str = 'failed') -> None:
        self.failure, self.state = failure, state

    def emit(self, event: OperationEvent) -> None:
        if self.sink is not None:
            try:
                self.sink(event)
            except Exception:
                logger.warning('operation observer failed', exc_info=True)

    def finish(self) -> None:
        if not self.finished:
            self.finished = True
            self.emit(replace(self.event, state=self.state, timestamp=time.time(),
                elapsed_seconds=max(0., time.monotonic() - self.event.started_monotonic), failure=self.failure))


def start_operation(stage: str, *, origin: str = 'core', **identity: str) -> OperationScope:
    """Observe an operation spanning generator yields without retaining ContextVar tokens."""
    context = replace(_current.get(), **identity)
    event = OperationEvent(observed_identifier(context.run_id or uuid4().hex), uuid4().hex,
        observed_identifier(context.parent_operation_id, optional=True),
        observed_identifier(stage), observed_identifier(origin), 'started', _CLOCK,
        time.monotonic(), time.time(), component_id=observed_identifier(context.component_id, optional=True),
        model_role=observed_identifier(context.model_role, optional=True), request_id=observed_identifier(context.request_id, optional=True),
        tool_call_id=observed_identifier(context.tool_call_id, optional=True), tool_name=observed_identifier(context.tool_name, optional=True))
    scope = OperationScope(event, context.sink)
    scope.emit(event)
    return scope


@contextmanager
def operation(stage: str, *, origin: str = 'core', **identity: str) -> Iterator[OperationScope]:
    context = replace(_current.get(), **identity)
    scope = start_operation(stage, origin=origin, **identity)
    event = scope.event
    try:
        with bind_observation(replace(context, run_id=event.run_id, parent_operation_id=event.operation_id)):
            yield scope
    except asyncio.CancelledError:
        scope.state = 'cancelled'
        raise
    except BaseException as exc:
        details = getattr(exc, 'details', None)
        failure = details.get('failure') if isinstance(details, dict) else None
        try:
            scope.fail(FailureInfo.from_dict(failure) if isinstance(failure, dict) else
                FailureInfo(origin, stage, 'timeout' if isinstance(exc, TimeoutError) else 'unknown',
                    'exception_type', exception_type=type(exc).__name__))
        except (ValueError, TypeError):
            scope.fail(FailureInfo(origin, stage))
        raise
    finally:
        scope.finish()
