"""Public experiment values. Private cases are never fields of editor requests."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from fruitfly_agent.improvement.contracts.pipeline import HarnessSnapshot, ImprovementOutcome, TaskMaterial, identifier, bounded
from fruitfly_agent.improvement.contracts.versions import content_hash, canonical_json
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.task_sets import TaskSetSnapshot


@dataclass(frozen=True)
class ExperimentSpec:
    source_id: str
    initial_harness_id: str
    initial_state_id: str
    conditions_id: str
    inner_components: tuple[str, ...]
    repetitions: int = 2
    max_depth: int = 2

    def __post_init__(self):
        from fruitfly_agent.improvement.contracts.versions import require_hash
        for value in (self.source_id, self.initial_harness_id, self.initial_state_id, self.conditions_id):
            require_hash(value)
        if type(self.repetitions) is not int or not 2 <= self.repetitions <= 10 or self.max_depth != 2:
            raise ValueError('improver experiments require 2–10 repeats and exactly two levels')
        if not self.inner_components or len(set(self.inner_components)) != len(self.inner_components):
            raise ValueError('declare distinct inner components')
        for name in self.inner_components:
            identifier(name)


@dataclass(frozen=True)
class EpisodeRequest:
    episode_id: str
    instructions: str
    baseline: HarnessSnapshot
    component_ids: tuple[str, ...]
    task: TaskMaterial
    repeat: int
    improver: HarnessSnapshot | None = None


@dataclass(frozen=True)
class EpisodeResult:
    episode_id: str
    outcome: ImprovementOutcome
    model_calls: int
    executions: int
    scores_before: tuple[float, ...] = ()
    scores_after: tuple[float, ...] = ()


class EpisodeMaterial(Protocol):
    @property
    def adaptation(self) -> TaskMaterial: ...
    @property
    def evaluations(self) -> tuple[Any, ...]: ...


class EpisodeExecutor(Protocol):
    async def run(self, request: EpisodeRequest, *, budget: Any, signal: Any) -> EpisodeResult: ...


@dataclass(frozen=True)
class TrialReport:
    experiment_id: str
    instructions_id: str
    initial_harness_id: str
    partition: str
    gains: tuple[float, ...]
    regressions: tuple[float, ...]
    failures: int
    model_calls: int
    executions: int
    episode_ids: tuple[str, ...]
    evidence: tuple[str, ...]
    schema_version: int = 1
    case_gains: tuple[tuple[float, ...], ...] = ()

    def __post_init__(self):
        import math
        from fruitfly_agent.improvement.contracts.versions import require_hash
        for value in (self.experiment_id, self.instructions_id, self.initial_harness_id, *self.evidence):
            require_hash(value)
        if self.schema_version != 1 or self.partition not in {'development', 'verification'}:
            raise ValueError('invalid trial report schema or partition')
        if len(self.gains) != len(self.episode_ids) or len(set(self.episode_ids)) != len(self.episode_ids):
            raise ValueError('trial report must retain every distinct episode')
        if any(type(v) is not int or v < 0 for v in (self.failures, self.model_calls, self.executions)):
            raise ValueError('invalid trial usage')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in (*self.gains, *self.regressions, *(x for row in self.case_gains for x in row))):
            raise ValueError('trial measurements must be finite')
        if self.case_gains and len(self.case_gains) != len(self.gains):
            raise ValueError('case measurements must cover each episode')

    @property
    def mean_gain(self):
        return sum(self.gains) / len(self.gains) if self.gains else 0.0


@dataclass(frozen=True)
class ExecutionRequest:
    instruction: str
    input_paths: tuple[str, ...]
    component_ids: tuple[str, ...]
    material_id: str
    scope: str
    feedback: str
    parameters: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class ExecutionParameter:
    name: str
    label: str
    kind: str
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    description: str = ''


@dataclass(frozen=True)
class MaterialOption:
    material_id: str
    label: str
    detail: str = ''
    error: str = ''


@dataclass
class PreparedExecution:
    task: TaskMaterial | TaskSetSnapshot
    source_id: str
    details: tuple[tuple[str, str], ...]
    current_source: Callable[[], str]
    private: Any = None
    minimum_budget: dict[str, int] = field(default_factory=dict)


@dataclass
class ExecutionPorts:
    runner: Any
    measurements: Any = None
    verifier: Any = None
    selector: Any = None
    verification_reserve: dict[str, int] = field(default_factory=lambda: {'model': 0, 'execution': 0})
    retain_experience: bool = True
    search_problem: Any = None


@dataclass(frozen=True)
class ExecutionDefinition:
    execution_id: str
    label: str
    implementation_id: str
    roles: frozenset[str]
    capabilities: frozenset[str]
    materials: Callable
    prepare: Callable
    build: Callable
    parameters: tuple[ExecutionParameter, ...] = ()
    notice: str = 'Explicit execution calls models; no activation occurs inside a trial.'
    defaults: tuple[tuple[str, Any], ...] = ()
    accepts_runner_override: bool = False
    plan_factory: Callable = RunPlan
    uses_configured_tools: bool = False

    def capabilities_for(self, tool_names):
        return self.capabilities | (frozenset("tool:" + name for name in tool_names) if self.uses_configured_tools else frozenset())

    def __post_init__(self):
        identifier(self.execution_id)
        identifier(self.implementation_id)
        bounded(self.label, 200)
        if not self.roles or self.roles - {'H', 'S', 'I'}:
            raise ValueError('invalid execution roles')
        if len({p.name for p in self.parameters}) != len(self.parameters):
            raise ValueError('duplicate execution parameters')

    def normalize(self, supplied):
        if len(dict(supplied)) != len(supplied):
            raise ValueError('duplicate execution parameter')
        values = dict(supplied)
        if set(values) - {p.name for p in self.parameters}:
            raise ValueError('unknown execution parameter')
        for p in self.parameters:
            value = values.setdefault(p.name, p.default)
            if p.kind == 'integer' and type(value) is not int:
                raise ValueError(p.name + ' must be an integer')
            if p.kind == 'string' and not isinstance(value, str):
                raise ValueError(p.name + ' must be a string')
            if p.kind == 'string' and len(value) > 6000:
                raise ValueError(p.name + ' exceeds its text allocation')
            if p.kind == 'number':
                import math
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(p.name + ' must be finite')
            if ((p.minimum is not None and value < p.minimum) or
                    (p.maximum is not None and value > p.maximum)):
                raise ValueError(p.name + ' is outside its allocation')
        return values
