"""One job-local state; plugins receive snapshots rather than this mutable owner."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowState:
    baseline: Any
    phase: str = 'preparing'
    round_index: int = -1
    seed: Any = None
    records: list[Any] = field(default_factory=list)
    candidates: list[Any] = field(default_factory=list)
    feedback: list[Any] = field(default_factory=list)
    harnesses: dict[str, Any] = field(default_factory=dict)
    selected: Any = None
    decision: Any = None
    selection_count: int = -1
    no_gain: int = 0
    failures: int = 0
    assessments: list[Any] = field(default_factory=list)
    exploration_decisions: list[Any] = field(default_factory=list)
    history: tuple[Any, ...] = ()
    seen: set[str] = field(default_factory=set)

    def __post_init__(self):
        self.seed = self.baseline
        self.harnesses[self.baseline.snapshot_id] = self.baseline
        self.seen.add(self.baseline.snapshot_id)
