"""Immutable execution facts. Unknown is distinct from zero or success."""
from dataclasses import asdict, dataclass
import math

from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.validation import bounded, identifier
from fruitfly_agent.improvement.contracts.versions import canonical_json, require_hash


@dataclass(frozen=True)
class BudgetFact:
    resource: str
    scope: str
    used: int | None = None
    limit: int | None = None
    source: str = ''

    def __post_init__(self):
        identifier(self.resource)
        if self.scope not in {'turn', 'execution', 'composite'}:
            raise ValueError('budget facts need an explicit accounting scope')
        for value in (self.used, self.limit):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError('budget facts require nonnegative counts or unknown')
        bounded(self.source, 500, empty=True)


@dataclass(frozen=True)
class ArtifactFact:
    path: str
    status: str
    source: str = ''
    artifact_id: str = ''

    def __post_init__(self):
        bounded(self.path, 2000)
        if self.status not in {'collected', 'absent', 'collection_failed', 'empty', 'unknown'}:
            raise ValueError('invalid artifact fact status')
        bounded(self.source, 500, empty=True)
        if self.artifact_id:
            require_hash(self.artifact_id)


@dataclass(frozen=True)
class ExecutionFacts:
    run_id: str
    task_id: str
    material_id: str
    harness_id: str
    conditions_id: str
    initial_state_id: str
    status: str
    termination_reason: str = 'unknown'
    budgets: tuple[BudgetFact, ...] = ()
    counters: tuple[tuple[str, int | None], ...] = ()
    artifacts: tuple[ArtifactFact, ...] = ()
    evidence: tuple[Resource, ...] = ()
    output_id: str = ''
    elapsed_seconds: float | None = None
    complete: bool = False
    children: tuple[str, ...] = ()
    schema_version: int = 1
    diagnosable: bool = False

    def __post_init__(self):
        identifier(self.run_id)
        identifier(self.task_id)
        for value in (self.material_id, self.harness_id, self.conditions_id, self.initial_state_id):
            require_hash(value)
        if self.schema_version != 1 or type(self.schema_version) is not int:
            raise ValueError('unsupported execution facts schema')
        if self.status not in {'completed', 'error', 'cancelled', 'budget_exhausted'}:
            raise ValueError('invalid execution facts status')
        identifier(self.termination_reason)
        for name in ('budgets', 'counters', 'artifacts', 'evidence', 'children'):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if len({name for name, value in self.counters}) != len(self.counters):
            raise ValueError('fact counters must be distinct')
        for name, count in self.counters:
            identifier(name)
            if count is not None and (type(count) is not int or count < 0):
                raise ValueError('fact counters require nonnegative counts or unknown')
        if len({(b.resource, b.scope) for b in self.budgets}) != len(self.budgets):
            raise ValueError('fact budgets must have distinct resources and scopes')
        if type(self.complete) is not bool:
            raise ValueError('fact completeness must be explicit')
        if type(self.diagnosable) is not bool:
            raise ValueError('diagnostic eligibility must be explicit')
        if self.elapsed_seconds is not None and (isinstance(self.elapsed_seconds, bool)
                or not isinstance(self.elapsed_seconds, (int, float))
                or not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0):
            raise ValueError('elapsed time must be finite, nonnegative or unknown')
        for reference in (*self.children, *((self.output_id,) if self.output_id else ())):
            require_hash(reference)

    def to_dict(self):
        return asdict(self)

    def serialize(self):
        return canonical_json(self.to_dict()).encode('utf-8')

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) - set(cls.__dataclass_fields__):
            raise ValueError('unknown execution facts fields')
        return cls(**{**value,
            'budgets': tuple(BudgetFact(**v) for v in value.get('budgets', ())),
            'counters': tuple(tuple(v) for v in value.get('counters', ())),
            'artifacts': tuple(ArtifactFact(**v) for v in value.get('artifacts', ())),
            'evidence': tuple(Resource(**v) for v in value.get('evidence', ()))})
