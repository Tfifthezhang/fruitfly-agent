"""Immutable outer-loop events and bounded context contributions."""
from dataclasses import dataclass
import json
from .tasks import Resource
from .validation import identifier
from .versions import canonical_json

HOOK_NAMES = frozenset({'before_run', 'before_proposal', 'after_candidate_validated',
    'before_trial', 'after_trial', 'after_round', 'before_finalization', 'before_run_end'})


@dataclass(frozen=True)
class LifecycleEvent:
    name: str
    job_id: str
    round_index: int
    phase: str
    snapshot_json: str

    def __post_init__(self):
        if self.name not in HOOK_NAMES:
            raise ValueError('unknown improvement lifecycle event')
        identifier(self.job_id)
        if type(self.round_index) is not int or self.round_index < -1:
            raise ValueError('invalid lifecycle round')
        if canonical_json(json.loads(self.snapshot_json)) != self.snapshot_json:
            raise ValueError('lifecycle snapshots must be canonical JSON')


@dataclass(frozen=True)
class ContextContribution:
    resources: tuple[Resource, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, 'resources', tuple(self.resources))
        if len(self.resources) > 32 or any(not isinstance(r, Resource) or r.kind != 'input' for r in self.resources):
            raise ValueError('context contributions require at most 32 input references')
        if len({r.path for r in self.resources}) != len(self.resources):
            raise ValueError('context contribution paths must be distinct')
