"""Improvement execution contracts and frontend views."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable
from fruitfly_agent.interactive.contracts.candidates import CandidateView, CandidateSection


@dataclass(frozen=True)
class ImprovementPreview:
    algorithm: str
    label: str
    cost_notice: str
    details: tuple[tuple[str, str], ...] = ()
    target: str = ''
    preview_token: str = ''
    role: str = 'H'


@dataclass(frozen=True)
class ImprovementTargetView:
    role: str
    target_id: str
    label: str
    available: bool = True
    reason: str = ''


class ImprovementService(Protocol):
    def improvement_preview(self, manifest: Mapping[str, object], *, pack_id=None, direction="", method_id=None, target_id=None, parameters=None) -> ImprovementPreview: ...
    async def improve(self, manifest: Mapping[str, object], direction: str, *, preview_token="") -> tuple[CandidateView, ...]: ...
    def cancel_improvement(self) -> bool: ...


@dataclass(frozen=True)
class ImprovementActivity:
    """Frontend-owned live activity, with no task answers or algorithm internals."""
    phase: str
    completed: int = 0
    total: int = 0
    model_calls: int = 0
    model_limit: int = 0
    trial_calls: int = 0
    trial_limit: int = 0
    failed_trials: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    usage_reported_calls: int = 0
    usage_missing_calls: int = 0


@runtime_checkable
class ImprovementActivityService(Protocol):
    def improvement_activity(self) -> ImprovementActivity | None: ...


@dataclass(frozen=True)
class ImprovementProgress:
    sequence: int
    status: str
    error: str = ''
    activity: ImprovementActivity | None = None


@runtime_checkable
class ImprovementClient(Protocol):
    """Frontend operations implemented by an Application with an injected service."""
    def improvement_preview(self, *, pack_id=None, direction="", method_id=None, target_id=None, parameters=None) -> ImprovementPreview: ...
    def start_improvement(self, direction: str, *, preview_token=""): ...




@dataclass(frozen=True)
class ImprovementMethodView:
    method_id: str
    label: str
    description: str
    available: bool = True
    reason: str = ''
    default: bool = False
    parameters: tuple[ImprovementParameterView, ...] = ()
    task_sources: tuple[str, ...] = ('saved',)
    requirements: tuple[tuple[str, str], ...] = ()
    direction_help: str = ''
    implementation_path: str = ''
    documentation_path: str = ''
    configuration_path: str = ''
    configuration_profile: str = ''


@dataclass(frozen=True)
class ImprovementParameterView:
    name: str
    label: str
    kind: str
    value: object = None
    minimum: float | None = None
    maximum: float | None = None
    group: str = 'parameters'
    description: str = ''
    choices: tuple[object, ...] = ()
    nullable: bool = False


@dataclass(frozen=True)
class ImprovementRunView:
    """One explicitly submitted experiment, including runs without candidates."""
    run_id: str
    status: str
    algorithm: str = ''
    target: str = ''
    role: str = 'H'
    direction: str = ''
    started_at: str = ''
    finished_at: str = ''
    stop_reason: str = ''
    candidate_ids: tuple[str, ...] = ()
    sections: tuple[CandidateSection, ...] = ()
    evidence: tuple[tuple[str, str], ...] = ()


@runtime_checkable
class ImprovementHistoryService(Protocol):
    def improvement_history(self) -> tuple[ImprovementRunView, ...]: ...


@runtime_checkable
class ImprovementLogService(Protocol):
    def improvement_run_logs(self, run_id: str) -> str: ...


class ImprovementSubmissionService(Protocol):
    """Optional host receipts; Application retains all execution authority."""
    def improvement_submitted(self, manifest: Mapping[str, object], direction: str, *, preview_token: str = '') -> str: ...
    def improvement_finished(self, preview_token: str, status: str, error: str = '') -> None: ...
