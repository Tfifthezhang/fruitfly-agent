"""Exploration decisions never replace official selection or grant adoption."""
from dataclasses import dataclass

from fruitfly_agent.improvement.contracts.versions import require_hash
from fruitfly_agent.improvement.contracts.validation import identifier, bounded


@dataclass(frozen=True)
class ExplorationDecision:
    run_id: str
    reason: str
    evidence_ids: tuple[str, ...] = ()
    policy_id: str = 'incumbent'

    def __post_init__(self):
        identifier(self.run_id)
        identifier(self.policy_id)
        bounded(self.reason, 4000)
        object.__setattr__(self, 'evidence_ids', tuple(self.evidence_ids))
        for value in self.evidence_ids:
            require_hash(value)
