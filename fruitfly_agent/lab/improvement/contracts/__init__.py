"""Role-neutral requests, target preparation and comparison evidence."""
from dataclasses import dataclass
from typing import Protocol, Any
from fruitfly_agent.lab.improvement.contracts.versions import SystemVersion
from fruitfly_agent.lab.improvement.contracts.candidates import VersionCandidate
from fruitfly_agent.lab.improvement.contracts.versions import require_hash


@dataclass(frozen=True)
class ImprovementRequest:
    """Freeze the target and external comparison conditions before generation."""
    role: str
    target_id: str
    parent: SystemVersion
    conditions_id: str
    policy_id: str
    direction: str

    def __post_init__(self):
        if self.role not in {'H', 'S', 'I'} or not self.target_id.strip():
            raise ValueError('a role and target are required')
        require_hash(self.conditions_id)
        if not self.policy_id.strip() or not isinstance(self.direction, str) or len(self.direction) > 500:
            raise ValueError('a fixed policy and bounded direction are required')


@dataclass(frozen=True)
class ComparisonEvidence:
    candidate_id: str
    conditions_id: str
    policy_id: str
    passed: bool

    def __post_init__(self):
        require_hash(self.candidate_id)
        require_hash(self.conditions_id)
        if type(self.passed) is not bool or not self.policy_id.strip():
            raise ValueError('comparison needs an explicit decision and policy')


class ImprovementAdapter(Protocol):
    """Target-owned resources; preparation must clean up partial construction."""
    async def prepare(self, request: ImprovementRequest, candidate: VersionCandidate) -> Any: ...
    async def close(self, trial: Any) -> None: ...


class ImprovementComparison(Protocol):
    async def compare(self, request: ImprovementRequest, candidate: VersionCandidate,
                      trial: Any) -> ComparisonEvidence: ...

