"""Immutable event, assessment and control values shared by execution backends."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from typing import AsyncIterator, Protocol

from fruitfly_agent.improvement.contracts.validation import identifier, bounded
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash, require_hash
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord


@dataclass(frozen=True)
class EvidencePosition:
    execution_id: str
    version_id: str
    segment_id: str
    sequence: int

    def __post_init__(self):
        identifier(self.execution_id)
        require_hash(self.version_id)
        identifier(self.segment_id)
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError('evidence sequence must be nonnegative')


@dataclass(frozen=True)
class ExecutionEvent:
    position: EvidencePosition
    kind: str
    payload_json: str = '{}'

    def __post_init__(self):
        identifier(self.kind)
        bounded(self.payload_json, 120000)
        value = json.loads(self.payload_json)
        if not isinstance(value, dict) or canonical_json(value) != self.payload_json:
            raise ValueError('event payload must be a canonical JSON object')

    @property
    def payload(self):
        return json.loads(self.payload_json)

    @property
    def event_id(self):
        return content_hash(canonical_json(asdict(self)))


@dataclass(frozen=True)
class Metric:
    name: str
    value: float | bool | str | None
    unit: str = ''

    def __post_init__(self):
        identifier(self.name)
        if self.value is not None and not isinstance(self.value, (int, float, bool, str)):
            raise ValueError('metric values must be scalars or unknown')
        if isinstance(self.value, (float, int)) and not isinstance(self.value, bool) and not math.isfinite(self.value):
            raise ValueError('metric values must be finite')
        bounded(self.unit, 100, empty=True)


@dataclass(frozen=True)
class Assessment:
    position: EvidencePosition
    assessor_id: str
    metrics: tuple[Metric, ...]
    status: str = 'provisional'
    scope: str = 'prefix'
    visibility: str = 'development'
    supersedes: str = ''
    detail: str = ''
    facts_id: str = ''
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self):
        identifier(self.assessor_id)
        object.__setattr__(self, 'metrics', tuple(self.metrics))
        if len({m.name for m in self.metrics}) != len(self.metrics):
            raise ValueError('assessment metrics must be distinct')
        if self.status not in {'provisional', 'final', 'incomplete', 'failed', 'unavailable'}:
            raise ValueError('invalid assessment status')
        if self.scope not in {'prefix', 'segment', 'execution'}:
            raise ValueError('invalid assessment scope')
        if self.visibility not in {'development', 'private'}:
            raise ValueError('invalid assessment visibility')
        if self.supersedes:
            require_hash(self.supersedes)
        bounded(self.detail, 4000, empty=True)
        if self.facts_id:
            require_hash(self.facts_id)
        object.__setattr__(self, 'evidence_ids', tuple(self.evidence_ids))
        for value in self.evidence_ids:
            require_hash(value)

    @property
    def assessment_id(self):
        return content_hash(canonical_json(asdict(self)))


@dataclass(frozen=True)
class ControlRequest:
    request_id: str
    action: str
    expected: EvidencePosition
    payload_json: str = '{}'
    max_event_lag: int = 0

    def __post_init__(self):
        identifier(self.request_id)
        identifier(self.action)
        if type(self.max_event_lag) is not int or self.max_event_lag < 0:
            raise ValueError('control lag must be nonnegative')
        bounded(self.payload_json, 24000)
        value = json.loads(self.payload_json)
        if not isinstance(value, dict) or canonical_json(value) != self.payload_json:
            raise ValueError('control payload must be a canonical JSON object')


@dataclass(frozen=True)
class ControlReceipt:
    request_id: str
    status: str
    reason: str

    def __post_init__(self):
        identifier(self.request_id)
        if self.status not in {'applied', 'rejected', 'unknown'}:
            raise ValueError('invalid control receipt')
        bounded(self.reason, 4000, empty=True)


class ExecutionHandle(Protocol):
    capabilities: frozenset[str]
    def events(self) -> AsyncIterator[ExecutionEvent]: ...
    async def result(self) -> ExecutionRecord: ...
    async def control(self, request: ControlRequest) -> ControlReceipt: ...
    async def aclose(self) -> None: ...


class OnlineAssessor(Protocol):
    assessor_id: str
    async def assess(self, event: ExecutionEvent) -> Assessment | None: ...


class ExecutionControlPolicy(Protocol):
    async def decide(self, assessment: Assessment) -> tuple[ControlRequest, ...]: ...
