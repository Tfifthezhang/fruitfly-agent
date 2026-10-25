"""Public editing contracts; no external effects."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Protocol
from .validation import identifier, relative_path, bounded
from .versions import canonical_json, content_hash, require_hash
import asyncio
from typing import Any, Awaitable, Literal, runtime_checkable, TYPE_CHECKING
from .tasks import TaskMaterial, ArtifactAccess
from .components import HarnessSnapshot
from .candidates import CandidateBundle
from .plans import RunPlan, ExperienceEntry
from .execution import ExecutionRecord
from .assessment import Measurement
from .task_sets import TaskEntry
from .evaluation import CandidateEvaluation
if TYPE_CHECKING:
    from .pipeline import ImprovementOutcome

@dataclass(frozen=True)
class ProposalRequest:
    plan: RunPlan
    task: TaskMaterial
    baseline: HarnessSnapshot
    records: tuple[ExecutionRecord, ...]
    scope: str
    index: int
    experience: tuple[ExperienceEntry, ...] = ()
    feedback: tuple[Measurement, ...] = ()
    history: tuple[CandidateBundle, ...] = ()


@dataclass(frozen=True)
class TaskSetProposalRequest:
    plan: RunPlan
    task_set_id: str
    tasks: tuple[TaskEntry, ...]
    baseline: HarnessSnapshot
    evaluations: tuple[CandidateEvaluation, ...]
    scope: str
    index: int
    history: tuple[CandidateBundle, ...] = ()
    experience: tuple[ExperienceEntry, ...] = ()

    @property
    def records(self):
        return tuple(t.record for e in self.evaluations for t in e.trials if t.record is not None)


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


class TaskSetCandidateGenerator(Protocol):
    generator_id: str
    required_capabilities: frozenset[str]
    supports_task_sets: bool
    async def propose(self, request: TaskSetProposalRequest, services: GenerationServices) -> ProposalResult: ...


@dataclass(frozen=True)
class GeneratorDefinition:
    generator_id: str
    implementation_id: str
    label: str
    required_capabilities: frozenset[str] = frozenset()
    supports_task_sets: bool = False

    def __post_init__(self):
        identifier(self.generator_id)
        identifier(self.implementation_id)
        if type(self.supports_task_sets) is not bool:
            raise ValueError('task-set generator capability must be boolean')
        bounded(self.label, 200)
        object.__setattr__(self, 'required_capabilities', frozenset(self.required_capabilities))


class Composer(Protocol):
    async def compose(self, request: CompositionRequest, services: GenerationServices) -> CandidateBundle: ...


class Reflector(Protocol):
    async def reflect(self, outcome: ImprovementOutcome) -> tuple[ExperienceEntry, ...]: ...


class ExperienceRepository(Protocol):
    def snapshot(self) -> tuple[ExperienceEntry, ...]: ...
    def commit(self, entries: tuple[ExperienceEntry, ...], *, expected_snapshot: str) -> str: ...


class EditorSession(Protocol):
    implementation_id: str
    async def edit(self, stage: str, request: ProposalRequest | CompositionRequest,
                   services: JobServices) -> CandidateBundle: ...

