"""Small values for host-injected recursive improvement orchestration."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal


@dataclass(frozen=True)
class AgentVersion:
    """Host-issued implementation references, not configuration or code hashes.

    The host must resolve these references to pinned task and improver artifacts.
    This value does not load code or attest the referenced implementation.
    """

    task_artifact: str
    improver_artifact: str

    def __post_init__(self) -> None:
        for value in (self.task_artifact, self.improver_artifact):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("artifact references must be non-empty strings")


@dataclass(frozen=True)
class Candidate:
    parent: AgentVersion
    version: AgentVersion
    rationale: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.parent, AgentVersion) or not isinstance(self.version, AgentVersion):
            raise TypeError("candidate parent/version must be AgentVersion values")
        if self.parent == self.version:
            raise ValueError("candidate must change task or improver artifact")
        if not isinstance(self.rationale, str):
            raise TypeError("candidate rationale must be text")


@dataclass(frozen=True)
class Verification:
    """Host verification bound to an exact candidate and explicit policy."""

    version: AgentVersion
    policy_id: str
    passed: bool
    feedback: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.version, AgentVersion):
            raise TypeError("verification version must be an AgentVersion")
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("verification policy_id must be non-empty")
        if not isinstance(self.passed, bool) or not isinstance(self.feedback, str):
            raise TypeError("verification requires boolean passed and text feedback")


@dataclass(frozen=True)
class EvolutionBudget:
    max_steps: int = 3
    phase_timeout_seconds: float = 60.0
    max_feedback_chars: int = 8_000

    def __post_init__(self) -> None:
        for name in ("max_steps", "max_feedback_chars"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        timeout = self.phase_timeout_seconds
        if (
            isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0
        ):
            raise ValueError("phase_timeout_seconds must be finite and positive")


EvolutionOutcome = Literal[
    "no_candidate", "invalid_candidate", "rejected", "verification_failed",
    "proposal_failed", "not_adopted", "adopted",
]


@dataclass(frozen=True)
class EvolutionAttempt:
    parent: AgentVersion
    candidate: Candidate | None
    verification: Verification | None
    outcome: EvolutionOutcome
    feedback: str = ""


@dataclass(frozen=True)
class EvolutionResult:
    version: AgentVersion
    attempts: tuple[EvolutionAttempt, ...]


__all__ = [
    "AgentVersion", "Candidate", "Verification", "EvolutionBudget",
    "EvolutionOutcome", "EvolutionAttempt", "EvolutionResult",
]
