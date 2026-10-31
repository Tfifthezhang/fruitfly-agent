"""Shared candidate evidence, adoption outcomes and durable evolution host boundary."""
from dataclasses import dataclass, field
import math
from typing import Protocol, Literal


@dataclass(frozen=True)
class VerificationEvidence:
    candidate_id: str
    artifact_id: str
    parent_manifest_digest: str
    policy_id: str
    passed: bool
    feedback: str = ''
    score: float | None = None

    def __post_init__(self):
        if not all(isinstance(v, str) and v for v in (self.candidate_id, self.artifact_id, self.parent_manifest_digest, self.policy_id)):
            raise ValueError('verification must bind candidate, content, parent and policy')
        if not isinstance(self.passed, bool):
            raise TypeError('verification passed must be boolean')
        if self.score is not None and (isinstance(self.score, bool) or not isinstance(self.score, (int, float)) or not math.isfinite(self.score)):
            raise ValueError('verification score must be finite or unknown')


@dataclass(frozen=True)
class AdoptionResult:
    status: Literal['planned', 'activated', 'rejected', 'stale', 'failed']
    manifest_digest: str = ''

    def __post_init__(self):
        if self.status not in {'planned', 'activated', 'rejected', 'stale', 'failed'}:
            raise ValueError('invalid adoption outcome')
        if self.status == 'activated' and not self.manifest_digest:
            raise ValueError('activation requires the actual manifest identity')


@dataclass(frozen=True)
class EvolutionJob:
    job_id: str
    policy_id: str
    direction: str
    current_manifest: str
    max_steps: int = 2
    steps: int = 0
    phase: str = 'ready'
    candidate_id: str = ''
    evidence: VerificationEvidence | None = None
    schema_version: int = 2
    strategy_id: str = ''
    stop_reason: str = ''
    consecutive_no_gain: int = 0
    consecutive_failures: int = 0
    elapsed_seconds: float = 0

    def __post_init__(self):
        if self.schema_version != 2 or isinstance(self.schema_version, bool):
            raise ValueError("unsupported evolution job schema")
        if not all(isinstance(v, str) and v for v in (self.job_id, self.policy_id, self.direction, self.current_manifest)):
            raise ValueError('evolution job identities and direction must not be empty')
        if isinstance(self.max_steps, bool) or not isinstance(self.max_steps, int) or self.max_steps < 1 or isinstance(self.steps, bool) or not isinstance(self.steps, int) or not 0 <= self.steps <= self.max_steps:
            raise ValueError('invalid evolution job step budget')
        if self.phase not in {'ready', 'proposing', 'proposed', 'verifying', 'verified', 'activating', 'complete', 'interrupted', 'planned', 'rejected', 'stale', 'failed'}:
            raise ValueError('invalid evolution job phase')
        if self.phase in {'proposed', 'verifying', 'verified', 'activating'} and not self.candidate_id:
            raise ValueError('evolution phase requires a fixed candidate')
        if self.phase in {'verified', 'activating'} and not isinstance(self.evidence, VerificationEvidence):
            raise ValueError('evolution phase requires verification evidence')
        if any(type(v) is not int or v < 0 for v in (self.consecutive_no_gain, self.consecutive_failures)):
            raise ValueError('evolution counters must be nonnegative integers')
        if isinstance(self.elapsed_seconds, bool) or not isinstance(self.elapsed_seconds, (int, float)) or not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise ValueError('evolution elapsed time must be finite and nonnegative')
        if not isinstance(self.stop_reason, str):
            raise ValueError('invalid evolution budget or stopping record')


class EvolutionHost(Protocol):
    def active_manifest(self) -> str: ...
    def load_job(self, job_id: str) -> EvolutionJob | None: ...
    def save_job(self, job: EvolutionJob) -> None: ...
    async def propose(self, direction: str) -> str | None: ...
    async def verify(self, candidate_id: str, policy_id: str) -> VerificationEvidence: ...
    async def adopt(self, candidate_id: str, evidence: VerificationEvidence) -> AdoptionResult: ...
    def is_active(self, candidate_id: str) -> bool: ...
