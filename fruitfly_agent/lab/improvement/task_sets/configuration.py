"""File-friendly batch settings with no backend or frontend dependencies."""
from dataclasses import dataclass, field, fields
import math
from typing import Any


def positive(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(name + ' must be a positive integer')


@dataclass(frozen=True)
class SamplingSettings:
    policy: str = 'stratified-cycle'
    batch_size: int = 8
    seed: int = 42
    task_keys: tuple[str, ...] = ()

    def __post_init__(self):
        if self.policy not in {'stratified-cycle', 'all', 'fixed'}:
            raise ValueError('unknown batch sampling policy')
        positive(self.batch_size, 'batch_size')
        if type(self.seed) is not int:
            raise ValueError('sampling seed must be an integer')
        object.__setattr__(self, 'task_keys', tuple(self.task_keys))
        if self.policy == 'fixed' and not self.task_keys:
            raise ValueError('fixed sampling needs task_keys')
        if len(set(self.task_keys)) != len(self.task_keys) or any(not isinstance(v, str) for v in self.task_keys):
            raise ValueError('task_keys must be distinct strings')


@dataclass(frozen=True)
class ParallelSettings:
    concurrency: int = 2
    candidate_concurrency: int = 1
    attempts: int = 1

    def __post_init__(self):
        positive(self.concurrency, 'concurrency')
        positive(self.attempts, 'attempts')
        if type(self.candidate_concurrency) is not int or self.candidate_concurrency != 1:
            raise ValueError('candidate concurrency currently supports only 1')


@dataclass(frozen=True)
class JointSettings:
    aggregation: str = 'collection-macro'
    weights: tuple[tuple[str, float], ...] = ()

    def __post_init__(self):
        if self.aggregation not in {'collection-macro', 'task-macro'}:
            raise ValueError('unknown joint aggregation')
        object.__setattr__(self, 'weights', tuple(tuple(v) for v in self.weights))
        if len(dict(self.weights)) != len(self.weights) or any(not isinstance(k, str)
                or isinstance(w, bool) or not isinstance(w, (float, int)) or not math.isfinite(w) or w <= 0
                for k, w in self.weights):
            raise ValueError('collection weights must be distinct, finite and positive')
        if self.aggregation == 'task-macro' and self.weights:
            raise ValueError('collection weights require collection-macro aggregation')


@dataclass(frozen=True)
class PromotionSettings:
    every_rounds: int = 3
    final_selection: str = 'all'
    minimum_gain: float = 0
    max_collection_regression: float | None = None

    def __post_init__(self):
        positive(self.every_rounds, 'every_rounds')
        if self.final_selection != 'all':
            raise ValueError('final_selection currently requires all declared selection tasks')
        if self.minimum_gain is None:
            raise ValueError('minimum_gain must be a finite nonnegative number')
        for name in ('minimum_gain', 'max_collection_regression'):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int))
                    or not math.isfinite(value) or value < 0):
                raise ValueError(name + ' must be finite and nonnegative')


@dataclass(frozen=True)
class MultiTaskSettings:
    sampling: SamplingSettings = field(default_factory=SamplingSettings)
    execution: ParallelSettings = field(default_factory=ParallelSettings)
    evaluation: JointSettings = field(default_factory=JointSettings)
    promotion: PromotionSettings = field(default_factory=PromotionSettings)

    @classmethod
    def from_dict(cls, raw):
        if not isinstance(raw, dict) or set(raw) - {f.name for f in fields(cls)}:
            raise ValueError('unknown multi_task fields')
        values: dict[str, Any] = {}
        for name, kind in (('sampling', SamplingSettings), ('execution', ParallelSettings),
                           ('evaluation', JointSettings), ('promotion', PromotionSettings)):
            data = raw.get(name, {})
            if not isinstance(data, dict) or set(data) - {f.name for f in fields(kind)}:
                raise ValueError('unknown multi_task.' + name + ' fields')
            data = dict(data)
            if name == 'sampling' and 'task_keys' in data and not isinstance(data['task_keys'], list):
                raise ValueError('task_keys must be a list')
            if name == 'evaluation' and 'weights' in data:
                if not isinstance(data['weights'], dict):
                    raise ValueError('weights must be a mapping')
                data['weights'] = tuple(sorted(data['weights'].items()))
            values[name] = kind(**data)
        return cls(**values)
