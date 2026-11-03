"""Immutable diagnostics; classification never grants retry or execution authority."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

from .validation import identifier, seconds


@dataclass(frozen=True)
class FailureCause:
    exception_type: str
    code: str = 'unknown'
    errno: int | None = None

    def __post_init__(self) -> None:
        identifier(self.exception_type)
        identifier(self.code)
        if self.errno is not None and type(self.errno) is not int:
            raise ValueError('cause errno must be an integer')


@dataclass(frozen=True)
class FailureInfo:
    origin: str
    stage: str
    code: str = 'unknown'
    evidence_kind: str = 'unknown'
    retry_disposition: str = 'unknown'
    effect_state: str = 'unknown'
    exception_type: str = ''
    causes: tuple[FailureCause, ...] = ()
    http_status: int | None = None

    def __post_init__(self) -> None:
        for name in ('origin', 'stage', 'code', 'evidence_kind', 'retry_disposition', 'effect_state', 'exception_type'):
            identifier(getattr(self, name), optional=name == 'exception_type')
        if not isinstance(self.causes, tuple) or len(self.causes) > 6 or any(not isinstance(cause, FailureCause) for cause in self.causes):
            raise ValueError('failure causes must be a bounded immutable chain')
        if self.http_status is not None and (type(self.http_status) is not int or not 100 <= self.http_status <= 599):
            raise ValueError('invalid failure HTTP status')

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> FailureInfo:
        copied = dict(value)
        if 'causes' in copied:
            copied['causes'] = tuple(FailureCause(**cause) for cause in copied['causes'])
        return cls(**copied)


@dataclass(frozen=True)
class OperationEvent:
    run_id: str
    operation_id: str
    parent_operation_id: str
    stage: str
    origin: str
    state: str
    clock_id: str
    started_monotonic: float
    timestamp: float
    elapsed_seconds: float | None = None
    component_id: str = ''
    model_role: str = ''
    request_id: str = ''
    tool_call_id: str = ''
    tool_name: str = ''
    failure: FailureInfo | None = None

    def __post_init__(self) -> None:
        for name in ('run_id', 'operation_id', 'stage', 'origin', 'clock_id'):
            identifier(getattr(self, name))
        for name in ('parent_operation_id', 'component_id', 'model_role', 'request_id', 'tool_call_id', 'tool_name'):
            identifier(getattr(self, name), optional=True)
        if self.state not in {'started', 'succeeded', 'failed', 'cancelled', 'skipped', 'cleanup_unconfirmed'}:
            raise ValueError('invalid operation state')
        seconds(self.started_monotonic)
        seconds(self.timestamp)
        if self.elapsed_seconds is not None:
            seconds(self.elapsed_seconds)
        if (self.state == 'started') != (self.elapsed_seconds is None):
            raise ValueError('only started operations have unknown duration')
        if self.failure is not None and not isinstance(self.failure, FailureInfo):
            raise ValueError('operation failure must be FailureInfo')

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> OperationEvent:
        copied = dict(value)
        if copied.get('failure') is not None:
            copied['failure'] = FailureInfo.from_dict(copied['failure'])
        return cls(**copied)


ObservationSink = Callable[[OperationEvent], None]
