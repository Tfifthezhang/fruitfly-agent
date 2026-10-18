"""Independent candidate review and activation contracts."""
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping, Protocol, runtime_checkable
if TYPE_CHECKING:
    from fruitfly_agent.interactive.contracts.runtime import RuntimeHandle


@dataclass(frozen=True)
class CandidateView:
    candidate_id: str
    status: str
    algorithm: str
    target: str
    artifact_id: str
    direction: str
    parent_manifest_digest: str
    evidence: tuple[tuple[str, str], ...] = ()
    sections: tuple[CandidateSection, ...] = ()
    role: str = 'H'
    assessment: str = ''


@dataclass(frozen=True)
class CandidateSection:
    title: str
    text: str
    summary: str = ''
    initial: bool = False


class CandidateActivationService(Protocol):
    """Host adapter that prepares an isolated runtime for one reviewed candidate."""
    async def prepare_candidate(self, manifest: Mapping[str, object], candidate_id: str) -> RuntimeHandle: ...


@runtime_checkable
class CandidateService(Protocol):
    def candidates(self) -> tuple[CandidateView, ...]: ...
    def candidate_notice(self) -> tuple[str, ...]: ...
    def acknowledge_candidate_notice(self, ids: tuple[str, ...]) -> None: ...
    def candidate_detail(self, candidate_id: str) -> tuple[CandidateView, str]: ...
    def candidate_action(self, manifest: Mapping[str, object], candidate_id: str, action: str) -> CandidateView: ...


@runtime_checkable
class CandidateClient(Protocol):
    def candidates(self) -> tuple[CandidateView, ...]: ...
    def candidate_notice(self) -> tuple[str, ...]: ...
    def acknowledge_candidate_notice(self, ids: tuple[str, ...]) -> None: ...
    def candidate_detail(self, candidate_id: str) -> tuple[CandidateView, str]: ...
    def candidate_action(self, candidate_id: str, action: str) -> CandidateView: ...


@runtime_checkable
class CandidateActivationClient(Protocol):
    """Optional frontend capability to activate a reviewed candidate now."""
    async def adopt_candidate(self, candidate_id: str) -> CandidateView: ...


