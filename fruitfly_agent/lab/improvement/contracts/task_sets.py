"""Frozen task collections and source bindings, independent of execution vendors."""
from dataclasses import asdict, dataclass
import math
from typing import Any, Callable

from .tasks import TaskMaterial
from .validation import identifier
from .versions import canonical_json, content_hash, require_hash


@dataclass(frozen=True)
class ScoreSpec:
    policy_id: str
    minimum: float = 0
    maximum: float = 1
    direction: str = 'max'

    def __post_init__(self):
        identifier(self.policy_id)
        if (self.direction not in {'min', 'max'} or any(isinstance(v, bool)
                or not isinstance(v, (float, int)) or not math.isfinite(v)
                for v in (self.minimum, self.maximum)) or self.minimum >= self.maximum):
            raise ValueError('declare a finite score range and direction')

    def normalize(self, value):
        if (isinstance(value, bool) or not isinstance(value, (float, int))
                or not math.isfinite(value) or not self.minimum <= value <= self.maximum):
            raise ValueError('task score is outside its declared range')
        score = (value - self.minimum) / (self.maximum - self.minimum)
        return score if self.direction == 'max' else 1 - score


@dataclass(frozen=True)
class TaskEntry:
    key: str
    collection_id: str
    source_id: str
    backend_id: str
    task: TaskMaterial
    objective: ScoreSpec
    origin_id: str
    group_id: str = ''
    partition: str = 'development'
    model_limit: int = 80
    execution_limit: int = 1

    def __post_init__(self):
        for value in (self.key, self.collection_id, self.backend_id):
            identifier(value)
        require_hash(self.source_id)
        if not isinstance(self.origin_id, str) or not self.origin_id:
            raise ValueError('a task needs a canonical source identity')
        if self.partition not in {'development', 'selection', 'confirmation'}:
            raise ValueError('invalid task partition')
        for allowance in (self.model_limit, self.execution_limit):
            if type(allowance) is not int or allowance < 1:
                raise ValueError('declare positive per-task model and leaf-execution allowances')


@dataclass(frozen=True)
class TaskSetSnapshot:
    entries: tuple[TaskEntry, ...]
    schema_version: int = 1

    def __post_init__(self):
        object.__setattr__(self, 'entries', tuple(self.entries))
        if type(self.schema_version) is not int or self.schema_version != 1 or not self.entries:
            raise ValueError('a task set needs schema 1 and nonempty entries')
        for values in ((e.key for e in self.entries), (e.task.task_id for e in self.entries),
                       (e.origin_id for e in self.entries)):
            items = tuple(values)
            if len(set(items)) != len(items):
                raise ValueError('duplicate task identity in task set')
        groups: dict[str, str] = {}
        for entry in self.entries:
            group = entry.group_id or entry.origin_id
            if group in groups and groups[group] != entry.partition:
                raise ValueError('task group leaks across partitions')
            groups[group] = entry.partition
        if not any(e.partition == 'development' for e in self.entries):
            raise ValueError('a task set needs development material')

    @property
    def snapshot_id(self):
        return content_hash(canonical_json(asdict(self)))

    def partition(self, name):
        return tuple(e for e in self.entries if e.partition == name)

    def selection_entries(self):
        explicit = {e.collection_id for e in self.entries if e.partition == 'selection'}
        return tuple(e for e in self.entries if e.partition == 'selection'
            or e.partition == 'development' and e.collection_id not in explicit)


@dataclass
class CollectionBinding:
    """Private construction callbacks never become editor material."""
    entries: tuple[TaskEntry, ...]
    build: Callable[[Any], Any]
    current_source: Callable[[], str]
    source_id: str
    capabilities: frozenset[str]
    roles: frozenset[str] = frozenset({'H', 'S'})


@dataclass(frozen=True)
class TaskSetSourceDefinition:
    source_id: str
    implementation_id: str
    freeze: Callable
