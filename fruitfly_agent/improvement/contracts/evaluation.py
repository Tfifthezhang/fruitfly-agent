"""Batch evaluations retain leaf receipts rather than inventing task executions."""
from dataclasses import asdict, dataclass

from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.assessment import Measurement
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash, require_hash
from fruitfly_agent.improvement.contracts.validation import identifier
from fruitfly_agent.improvement.contracts.task_sets import TaskSetSnapshot
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.components import HarnessSnapshot
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle
import math


@dataclass(frozen=True)
class EvaluationBatch:
    task_set_id: str
    task_keys: tuple[str, ...]
    phase: str = 'search'
    attempts: int = 1

    def __post_init__(self):
        require_hash(self.task_set_id)
        object.__setattr__(self, 'task_keys', tuple(self.task_keys))
        if not self.task_keys or len(set(self.task_keys)) != len(self.task_keys):
            raise ValueError('a batch needs distinct expected task keys')
        for key in self.task_keys:
            identifier(key)
        if self.phase not in {'search', 'selection', 'confirmation'}:
            raise ValueError('invalid evaluation phase')
        if type(self.attempts) is not int or self.attempts < 1:
            raise ValueError('attempts must be a positive integer')

    @property
    def batch_id(self):
        return content_hash(canonical_json(asdict(self)))


@dataclass(frozen=True)
class TrialResult:
    task_key: str
    attempt: int
    record: ExecutionRecord | None
    measurement: Measurement | None
    error: str = ''

    def __post_init__(self):
        identifier(self.task_key)
        if type(self.attempt) is not int or self.attempt < 0:
            raise ValueError('trial attempt must be nonnegative')
        if self.measurement is not None and (self.record is None or self.measurement.run_id != self.record.run_id):
            raise ValueError('measurement differs from trial receipt')


@dataclass(frozen=True)
class JointAssessment:
    score: float | None
    collections: tuple[tuple[str, float], ...]
    tasks: tuple[tuple[str, float], ...]
    expected: int
    completed: int
    aggregation: str
    weights: tuple[tuple[str, float], ...] = ()

    def __post_init__(self):
        if (type(self.expected) is not int or type(self.completed) is not int
                or not 0 <= self.completed <= self.expected):
            raise ValueError('invalid joint assessment coverage')
        if self.score is not None and (isinstance(self.score, bool) or not isinstance(self.score, (int, float))
                or not math.isfinite(self.score) or not 0 <= self.score <= 1 or self.completed != self.expected):
            raise ValueError('joint utility needs complete finite normalized evidence')


@dataclass(frozen=True)
class CandidateEvaluation:
    evaluation_id: str
    harness_id: str
    conditions_id: str
    batch: EvaluationBatch
    trials: tuple[TrialResult, ...]
    assessment: JointAssessment

    def __post_init__(self):
        identifier(self.evaluation_id)
        require_hash(self.harness_id)
        require_hash(self.conditions_id)
        object.__setattr__(self, 'trials', tuple(self.trials))
        expected = {(key, attempt) for key in self.batch.task_keys for attempt in range(self.batch.attempts)}
        actual = [(t.task_key, t.attempt) for t in self.trials]
        if len(actual) != len(set(actual)) or set(actual) - expected:
            raise ValueError('unexpected or duplicate trial result')
        if any(t.record is not None and (t.record.harness_id != self.harness_id
                or t.record.conditions_id != self.conditions_id) for t in self.trials):
            raise ValueError('batch leaf differs from candidate or conditions')

    @property
    def complete(self):
        return self.assessment.score is not None


@dataclass(frozen=True)
class CandidateComparison:
    before_id: str
    after_id: str
    batch_id: str
    result: str
    gain: float | None = None

    def __post_init__(self):
        for name in (self.before_id, self.after_id):
            identifier(name)
        require_hash(self.batch_id)
        if self.result not in {'better', 'worse', 'tied', 'insufficient'}:
            raise ValueError('invalid candidate comparison')


@dataclass(frozen=True)
class JointSelection:
    evaluation_id: str
    reason: str
    assurance: str = 'selected'

    def __post_init__(self):
        identifier(self.evaluation_id)
        if self.assurance != 'selected':
            raise ValueError('joint development selection cannot claim independent verification')


@dataclass(frozen=True)
class TaskSetOutcome:
    plan: RunPlan
    task_set: TaskSetSnapshot
    selected: CandidateEvaluation | None
    harness: HarnessSnapshot
    candidates: tuple[CandidateBundle, ...]
    records: tuple[CandidateEvaluation, ...]
    decision: JointSelection | None
    stop_reason: str = 'completed'
    exploration: tuple[dict[str, str], ...] = ()
    experience: tuple = ()
    verification: str = ''
