"""Attributed measurements and planned attempts; neither grants task success."""
from dataclasses import asdict, dataclass, field
from math import isfinite

from .research import ObservationSemantics
from .validation import identifier
from .versions import require_hash


@dataclass(frozen=True)
class PlannedAttempt:
    task_id: str
    attempt: int

    def __post_init__(self):
        identifier(self.task_id)
        if type(self.attempt) is not int or self.attempt < 0:
            raise ValueError('attempt must be a nonnegative integer')


@dataclass(frozen=True)
class BatchManifest:
    planned: tuple[PlannedAttempt, ...]
    purpose: str = 'development'
    origins: tuple[tuple[str, str], ...] = ()
    selection_reason: str = 'explicit task collection'
    scope_kind: str = 'declared'

    def __post_init__(self):
        object.__setattr__(self, 'planned', tuple(self.planned))
        if not self.planned or any(not isinstance(p, PlannedAttempt) for p in self.planned):
            raise ValueError('a batch needs planned task attempts')
        if len(set(self.planned)) != len(self.planned):
            raise ValueError('duplicate planned task attempt')
        if self.purpose not in {'development', 'selection', 'confirmation'}:
            raise ValueError('unknown batch purpose')
        object.__setattr__(self, 'origins', tuple(tuple(p) for p in self.origins))
        if len(dict(self.origins)) != len(self.origins):
            raise ValueError('duplicate task origin')
        if any(k not in {p.task_id for p in self.planned} or not isinstance(v, str) or not v for k, v in self.origins):
            raise ValueError('origin must identify a planned task')
        if len(set(dict(self.origins).values())) != len(self.origins):
            raise ValueError('task origins must be unique')
        if not isinstance(self.selection_reason, str) or not self.selection_reason.strip():
            raise ValueError('selection reason must be explicit')
        if self.scope_kind not in {'declared', 'retained-planned', 'retained-observed'}:
            raise ValueError('invalid plan scope kind')

    def to_dict(self):
        return {'kind': 'batch_manifest', **asdict(self)}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {'kind', 'planned', 'purpose', 'origins', 'selection_reason', 'scope_kind'} or value['kind'] != 'batch_manifest':
            raise ValueError('invalid batch manifest')
        return cls(tuple(PlannedAttempt(**row) for row in value['planned']), value['purpose'],
                   tuple(tuple(row) for row in value['origins']), value['selection_reason'], value['scope_kind'])


@dataclass(frozen=True)
class MeasurementObservation:
    run_id: str
    task_id: str
    attempt: int
    name: str
    value: float | None
    eligible: bool
    semantics: ObservationSemantics
    scorer_id: str | None
    outcome_policy_id: str
    source_identity: str | None
    unavailable_reason: str = ''
    raw_value: object = None
    unit: str = 'score'
    official_status: str | None = None
    error: dict | None = None
    elapsed_seconds: float | None = None
    comparison: dict = field(default_factory=dict)
    cost_usd: float | None = None

    def __post_init__(self):
        identifier(self.run_id)
        PlannedAttempt(self.task_id, self.attempt)
        identifier(self.name)
        require_hash(self.outcome_policy_id)
        for reference in (self.scorer_id, self.source_identity):
            if reference is not None:
                require_hash(reference)
        if type(self.eligible) is not bool or not isinstance(self.semantics, ObservationSemantics):
            raise ValueError('measurement needs explicit eligibility and semantics')
        if self.value is not None and (type(self.value) not in (int, float) or not isfinite(self.value)):
            raise ValueError('measurement must be finite or unknown')
        if self.eligible and self.value is None:
            raise ValueError('eligible measurement requires a value')
        if not self.eligible and self.semantics.outcome != 'unknown':
            raise ValueError('ineligible measurement cannot establish acceptance')
        if not isinstance(self.unavailable_reason, str):
            raise ValueError('measurement reason must be text')
        if not isinstance(self.unit, str) or not self.unit:
            raise ValueError('measurement unit must be declared')
        if self.official_status not in {None, 'passed', 'failed', 'error'}:
            raise ValueError('unknown official status')
        if self.error is not None and not isinstance(self.error, dict):
            raise ValueError('measurement error must be structured')
        if self.elapsed_seconds is not None and (type(self.elapsed_seconds) not in (int, float)
                or not isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0):
            raise ValueError('elapsed time must be finite and nonnegative')
        if self.cost_usd is not None and (type(self.cost_usd) not in (int, float)
                or not isfinite(self.cost_usd) or self.cost_usd < 0):
            raise ValueError('cost must be finite nonnegative USD or unknown')
        if not isinstance(self.comparison, dict) or set(self.comparison) - {'material', 'conditions', 'initial_state', 'source'}:
            raise ValueError('invalid comparison provenance')
        for key in ('material', 'conditions', 'initial_state'):
            if self.comparison.get(key) is not None:
                require_hash(self.comparison[key])
        from .versions import canonical_json
        canonical_json(self.raw_value)

    def to_dict(self):
        return {'kind': 'measurement', **asdict(self)}

    @classmethod
    def from_dict(cls, value):
        fields = set(cls.__dataclass_fields__)
        if not isinstance(value, dict) or set(value) != fields | {'kind'} or value['kind'] != 'measurement':
            raise ValueError('invalid measurement observation')
        return cls(**{**{k: value[k] for k in fields}, 'semantics': ObservationSemantics(**value['semantics'])})
