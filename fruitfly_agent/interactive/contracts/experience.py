"""Explicit review of attributed lessons, independent of candidate activation."""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PendingExperienceView:
    job_id: str
    initial_snapshot: str
    lessons: tuple[str, ...]
    details: tuple[tuple[str, str], ...] = ()


@runtime_checkable
class ExperienceReviewClient(Protocol):
    def pending_experience(self) -> tuple[PendingExperienceView, ...]: ...
    def experience_action(self, job_id: str, action: str) -> str: ...
