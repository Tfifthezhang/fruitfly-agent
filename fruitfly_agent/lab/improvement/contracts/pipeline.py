"""Immutable values and ports for evidence-driven component improvement.

Executions need no score. Generators cannot activate candidates or change the
frozen task, conditions, verification policy or resource allocation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any, Awaitable, Literal, Protocol, runtime_checkable
import asyncio
import math
import re

from .versions import SystemVersion, canonical_json, content_hash, require_hash


def identifier(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value):
        raise ValueError('a stable identifier is required')


def relative_path(value: str) -> None:
    if (not isinstance(value, str) or not value or '\\' in value
            or PurePosixPath(value).is_absolute() or any(p in {'', '.', '..'} for p in value.split('/'))
            or any(ord(c) < 32 for c in value)):
        raise ValueError('an owned relative file path is required')


def bounded(value: str, maximum=120_000, *, empty=False) -> None:
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ValueError('text must fit its declared bound')


@dataclass(frozen=True)
class Resource:
    path: str
    artifact_id: str
    media_type: str = 'text/plain; charset=utf-8'
    kind: str = 'input'

    def __post_init__(self):
        relative_path(self.path)
        require_hash(self.artifact_id)
        bounded(self.media_type, 200)
        if self.kind not in {'input', 'trajectory', 'deliverable', 'diagnostic'}:
            raise ValueError('invalid resource role')


@dataclass(frozen=True)
class TaskMaterial:
    task_id: str
    instruction: str
    inputs: tuple[Resource, ...] = ()
    environment_id: str = 'isolated-local'
    origin: str = 'interaction'

    def __post_init__(self):
        identifier(self.task_id)
        bounded(self.instruction)
        bounded(self.environment_id, 500)
        bounded(self.origin, 1000)
        object.__setattr__(self, 'inputs', tuple(self.inputs))
        if len({r.path for r in self.inputs}) != len(self.inputs):
            raise ValueError('task input paths must be distinct')

    @property
    def material_id(self):
        return content_hash(canonical_json(asdict(self)))


@dataclass(frozen=True)
class ComponentFile:
    path: str
    text: str

    def __post_init__(self):
        relative_path(self.path)
        bounded(self.text, 120_000, empty=True)


@dataclass(frozen=True)
class ComponentDocument:
    component_id: str
    kind: str
    role: Literal['H', 'S', 'I']
    schema: str
    files: tuple[ComponentFile, ...]

    def __post_init__(self):
        for value in (self.component_id, self.kind, self.schema):
            identifier(value)
        if self.role not in {'H', 'S', 'I'}:
            raise ValueError('component axis must be H, S or I')
        object.__setattr__(self, 'files', tuple(sorted(self.files, key=lambda f: f.path)))
        if len({f.path for f in self.files}) != len(self.files):
            raise ValueError('component file paths must be distinct')

    @property
    def document_id(self):
        return content_hash(canonical_json(asdict(self)))


@dataclass(frozen=True)
class HarnessSnapshot:
    components: tuple[ComponentDocument, ...]

    def __post_init__(self):
        object.__setattr__(self, 'components', tuple(sorted(self.components, key=lambda c: c.component_id)))
        if not self.components or len({c.component_id for c in self.components}) != len(self.components):
            raise ValueError('a harness needs distinct registered components')

    @property
    def snapshot_id(self):
        return content_hash(canonical_json(asdict(self)))

    def component(self, component_id):
        try:
            return next(c for c in self.components if c.component_id == component_id)
        except StopIteration as exc:
            raise ValueError('unregistered component: ' + component_id) from exc

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {'components'}:
            raise ValueError('invalid harness snapshot')
        return cls(tuple(ComponentDocument(**{**c, 'files': tuple(ComponentFile(**f) for f in c['files'])})
                         for c in value['components']))


@dataclass(frozen=True)
class EditReason:
    component_id: str
    explanation: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self):
        identifier(self.component_id)
        bounded(self.explanation, 4000)
        object.__setattr__(self, 'evidence_ids', tuple(self.evidence_ids))
        if not self.evidence_ids or any(not isinstance(v, str) or not v for v in self.evidence_ids):
            raise ValueError('edits need attributable evidence')


@dataclass(frozen=True)
class CandidateBundle:
    parent: SystemVersion
    base: HarnessSnapshot
    harness: HarnessSnapshot
    generator_id: str
    reasons: tuple[EditReason, ...] = ()

    def __post_init__(self):
        identifier(self.generator_id)
        object.__setattr__(self, 'reasons', tuple(self.reasons))
        if {c.component_id for c in self.base.components} != {c.component_id for c in self.harness.components}:
            raise ValueError('candidates must preserve the registered component set')
        for c in self.harness.components:
            old = self.base.component(c.component_id)
            if (c.kind, c.role, c.schema) != (old.kind, old.role, old.schema):
                raise ValueError('candidates cannot change component ownership or schema')

    @property
    def changed_ids(self):
        return tuple(c.component_id for c in self.harness.components if c != self.base.component(c.component_id))

    @property
    def changed_roles(self):
        return frozenset(self.harness.component(v).role for v in self.changed_ids)

    @property
    def candidate_id(self):
        return content_hash(canonical_json(asdict(self)))


@dataclass(frozen=True)
class ExecutionRecord:
    run_id: str
    task_id: str
    material_id: str
    harness_id: str
    initial_state_id: str
    conditions_id: str
    status: Literal['completed', 'error', 'cancelled', 'budget_exhausted']
    output: str = ''
    artifacts: tuple[Resource, ...] = ()
    model_calls: int | None = None

    def __post_init__(self):
        for value in (self.run_id, self.task_id):
            identifier(value)
        for value in (self.material_id, self.harness_id, self.initial_state_id, self.conditions_id):
            require_hash(value)
        if self.status not in {'completed', 'error', 'cancelled', 'budget_exhausted'}:
            raise ValueError('invalid execution status')
        bounded(self.output, 120_000, empty=True)
        object.__setattr__(self, 'artifacts', tuple(self.artifacts))
        if self.model_calls is not None and (type(self.model_calls) is not int or self.model_calls < 0):
            raise ValueError('invocation usage must be known nonnegative or absent')


@dataclass(frozen=True)
class Measurement:
    run_id: str
    policy_id: str
    score: float
    feedback: str = ''

    def __post_init__(self):
        identifier(self.run_id)
        identifier(self.policy_id)
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)) or not math.isfinite(self.score):
            raise ValueError('measurements require a finite score')
        bounded(self.feedback, 4000, empty=True)


@dataclass(frozen=True)
class RunPlan:
    job_id: str
    parent: SystemVersion
    component_ids: tuple[str, ...]
    generator_id: str = 'agent-editor-v1'
    mode: Literal['parallel', 'sequential'] = 'parallel'
    width: int = 1
    depth: int = 1
    purpose: Literal['task', 'persistent'] = 'task'
    feedback: Literal['behavior', 'scored'] = 'behavior'
    max_model_calls: int = 64
    max_executions: int = 32
    operation_timeout: float = 120
    direction: str = ''

    def __post_init__(self):
        identifier(self.job_id)
        identifier(self.generator_id)
        object.__setattr__(self, 'component_ids', tuple(self.component_ids))
        if not self.component_ids or len(set(self.component_ids)) != len(self.component_ids):
            raise ValueError('declare a distinct nonempty component scope')
        for component_id in self.component_ids:
            identifier(component_id)
        if self.mode not in {'parallel', 'sequential'} or self.purpose not in {'task', 'persistent'}:
            raise ValueError('invalid improvement mode or purpose')
        if self.feedback not in {'behavior', 'scored'}:
            raise ValueError('invalid feedback capability')
        for value, maximum in ((self.width, 10), (self.depth, 10), (self.max_model_calls, 10000), (self.max_executions, 1000)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError('improvement allocation exceeds its bound')
        if (isinstance(self.operation_timeout, bool) or not isinstance(self.operation_timeout, (int, float))
                or not math.isfinite(self.operation_timeout) or not 0 < self.operation_timeout <= 14400):
            raise ValueError('a bounded operation timeout is required')
        bounded(self.direction, 2000, empty=True)

    @property
    def conditions_id(self):
        return content_hash(canonical_json(asdict(self)))


@dataclass(frozen=True)
class ExperienceEntry:
    entry_id: str
    task_id: str
    cue: str
    lesson: str
    evidence_ids: tuple[str, ...]
    harness: HarnessSnapshot
    limitations: str = ''

    def __post_init__(self):
        identifier(self.entry_id)
        identifier(self.task_id)
        bounded(self.cue, 2000)
        bounded(self.lesson, 6000)
        bounded(self.limitations, 4000, empty=True)
        object.__setattr__(self, 'evidence_ids', tuple(self.evidence_ids))
        if not self.evidence_ids:
            raise ValueError('retained lessons need execution evidence')


@dataclass(frozen=True)
class ProposalRequest:
    plan: RunPlan
    task: TaskMaterial
    baseline: HarnessSnapshot
    records: tuple[ExecutionRecord, ...]
    scope: Literal['invariant', 'domain']
    index: int
    experience: tuple[ExperienceEntry, ...] = ()
    feedback: tuple[Measurement, ...] = ()
    history: tuple[CandidateBundle, ...] = ()


@dataclass(frozen=True)
class ProposalResult:
    candidates: tuple[CandidateBundle, ...] = ()
    stop: bool = False

    def __post_init__(self):
        object.__setattr__(self, 'candidates', tuple(self.candidates))
        if len(self.candidates) > 10 or type(self.stop) is not bool:
            raise ValueError('a proposal batch needs at most ten candidates and an explicit stop flag')


@dataclass(frozen=True)
class CompositionRequest:
    plan: RunPlan
    task: TaskMaterial
    baseline: HarnessSnapshot
    candidates: tuple[CandidateBundle, ...]
    records: tuple[ExecutionRecord, ...]
    index: int
    experience: tuple[ExperienceEntry, ...] = ()
    feedback: tuple[Measurement, ...] = ()


@dataclass(frozen=True)
class SelectionDecision:
    run_id: str
    reason: str
    assurance: Literal['selected', 'verified'] = 'selected'

    def __post_init__(self):
        identifier(self.run_id)
        bounded(self.reason, 4000)
        if self.assurance not in {'selected', 'verified'}:
            raise ValueError('selection assurance must be explicit')


@dataclass(frozen=True)
class ImprovementOutcome:
    plan: RunPlan
    task: TaskMaterial
    selected: ExecutionRecord | None
    harness: HarnessSnapshot
    candidates: tuple[CandidateBundle, ...]
    records: tuple[ExecutionRecord, ...]
    decision: SelectionDecision | None
    experience: tuple[ExperienceEntry, ...] = ()
    stop_reason: str = 'completed'
    verification: str = ''


class ArtifactAccess(Protocol):
    def put(self, content: bytes) -> str: ...
    def read(self, artifact_id: str) -> bytes: ...


class ComponentAdapter(Protocol):
    def snapshot(self) -> ComponentDocument: ...
    def validate(self, document: ComponentDocument) -> None: ...


class GenerationServices(Protocol):
    def check(self) -> None: ...
    def record(self, event: str, **fields: object) -> None: ...
    async def edit(self, stage: str, request: ProposalRequest | CompositionRequest) -> CandidateBundle: ...
    async def complete(self, system: str, prompt: str) -> str: ...


class JobServices(GenerationServices, Protocol):
    """Execution/editor host ports; generators receive the narrower service view."""
    plan: RunPlan
    signal: asyncio.Event
    def reserve(self, kind: str, amount: int = 1) -> None: ...
    async def operation(self, awaitable: Awaitable[Any]) -> Any: ...
    def own(self, resource: Any) -> Any: ...


class JobResource(Protocol):
    """Optional per-job factory product lifecycle; borrowed ports are not closed."""
    async def aclose(self) -> None: ...


class EditorWorkspace(Protocol):
    def paths(self) -> tuple[str, ...]: ...
    def read(self, path: str) -> bytes: ...
    def write(self, path: str, text: str) -> None: ...
    def delete(self, path: str) -> None: ...


class InspectionInstructions(Protocol):
    select: str
    reflect: str


@runtime_checkable
class EvidenceInspector(Protocol):
    artifacts: ArtifactAccess
    instructions: InspectionInstructions
    async def session(self, mission: str, workspace: EditorWorkspace, services: JobServices,
                      *, writable: bool = False) -> str: ...


class CandidateGenerator(Protocol):
    generator_id: str
    required_capabilities: frozenset[str]
    async def propose(self, request: ProposalRequest, services: GenerationServices) -> ProposalResult: ...


@dataclass(frozen=True)
class GeneratorDefinition:
    generator_id: str
    implementation_id: str
    label: str
    required_capabilities: frozenset[str] = frozenset()

    def __post_init__(self):
        identifier(self.generator_id)
        identifier(self.implementation_id)
        bounded(self.label, 200)
        object.__setattr__(self, 'required_capabilities', frozenset(self.required_capabilities))


class Composer(Protocol):
    async def compose(self, request: CompositionRequest, services: GenerationServices) -> CandidateBundle: ...


class TaskRunner(Protocol):
    capabilities: frozenset[str]
    async def execute(self, plan: RunPlan, task: TaskMaterial, harness: HarnessSnapshot) -> ExecutionRecord: ...


class Selector(Protocol):
    async def select(self, task: TaskMaterial, records: tuple[ExecutionRecord, ...]) -> SelectionDecision: ...


class Reflector(Protocol):
    async def reflect(self, outcome: ImprovementOutcome) -> tuple[ExperienceEntry, ...]: ...


class MeasurementSource(Protocol):
    async def measure(self, task: TaskMaterial, record: ExecutionRecord) -> Measurement | None: ...


class ExperienceRepository(Protocol):
    def snapshot(self) -> tuple[ExperienceEntry, ...]: ...
    def commit(self, entries: tuple[ExperienceEntry, ...], *, expected_snapshot: str) -> str: ...


class VerificationPolicy(Protocol):
    async def verify(self, outcome: ImprovementOutcome) -> SelectionDecision | None: ...


class EditorSession(Protocol):
    implementation_id: str
    async def edit(self, stage: str, request: ProposalRequest | CompositionRequest,
                   services: JobServices) -> CandidateBundle: ...


class WorkflowController(Protocol):
    async def run(self, plan: RunPlan, task: TaskMaterial, baseline: HarnessSnapshot,
                  services: JobServices, *, experience: tuple[ExperienceEntry, ...] = ()) -> ImprovementOutcome: ...


class TaskSource(Protocol):
    def freeze(self, task_id: str, instruction: str, *, paths=(),
               environment_id: str = 'isolated-local') -> TaskMaterial: ...


def experience_id(entries):
    return content_hash(canonical_json([asdict(e) for e in entries]))
