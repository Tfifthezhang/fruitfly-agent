"""Frontend-owned presentation and optional optimization service contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .application import RuntimeHandle


@dataclass(frozen=True)
class OptimizationPreview:
    algorithm: str
    label: str
    cost_notice: str
    details: tuple[tuple[str, str], ...] = ()
    target: str = ''
    preview_token: str = ''


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


@dataclass(frozen=True)
class CandidateSection:
    title: str
    text: str
    summary: str = ''
    initial: bool = False


class OptimizationService(Protocol):
    def optimization_preview(self, manifest: Mapping[str, object], *, pack_id=None, direction="") -> OptimizationPreview: ...
    async def optimize(self, manifest: Mapping[str, object], direction: str, *, preview_token="") -> tuple[CandidateView, ...]: ...
    def cancel_optimization(self) -> bool: ...
    def candidates(self) -> tuple[CandidateView, ...]: ...
    def candidate_notice(self) -> tuple[str, ...]: ...
    def acknowledge_candidate_notice(self, ids: tuple[str, ...]) -> None: ...
    def candidate_detail(self, candidate_id: str) -> tuple[CandidateView, str]: ...
    def candidate_action(self, manifest: Mapping[str, object], candidate_id: str, action: str) -> CandidateView: ...


class CandidateActivationService(Protocol):
    """Host adapter that prepares an isolated runtime for one reviewed candidate."""
    async def prepare_candidate(self, manifest: Mapping[str, object], candidate_id: str) -> RuntimeHandle: ...


@dataclass(frozen=True)
class OptimizationActivity:
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
class OptimizationActivityService(Protocol):
    def optimization_activity(self) -> OptimizationActivity | None: ...


@dataclass(frozen=True)
class OptimizationProgress:
    sequence: int
    status: str
    error: str = ''
    activity: OptimizationActivity | None = None


@runtime_checkable
class OptimizationClient(Protocol):
    """Frontend operations implemented by an Application with an injected service."""
    def optimization_preview(self, *, pack_id=None, direction="") -> OptimizationPreview: ...
    def start_optimization(self, direction: str, *, preview_token=""): ...
    def candidates(self) -> tuple[CandidateView, ...]: ...
    def candidate_notice(self) -> tuple[str, ...]: ...
    def acknowledge_candidate_notice(self, ids: tuple[str, ...]) -> None: ...
    def candidate_detail(self, candidate_id: str) -> tuple[CandidateView, str]: ...
    def candidate_action(self, candidate_id: str, action: str) -> CandidateView: ...


@runtime_checkable
class CandidateActivationClient(Protocol):
    """Optional frontend capability to activate a reviewed candidate now."""
    async def adopt_candidate(self, candidate_id: str) -> CandidateView: ...


@dataclass(frozen=True)
class TaskPackView:
    pack_id: str
    name: str
    source_hash: str
    train_count: int
    validation_count: int
    holdout_count: int
    writable: bool
    error: str = ""
    default_direction: str = ""
    acceptance_example: str = ""


@dataclass(frozen=True)
class CorrectionView:
    task_id: str
    input: str
    output: str
    context_warning: bool = False


@runtime_checkable
class TaskPackClient(Protocol):
    @property
    def task_packs_available(self) -> bool: ...
    def task_packs(self) -> tuple[TaskPackView, ...]: ...
    def correction_tasks(self) -> tuple[CorrectionView, ...]: ...
    def save_training_task(self, task_id: str, pack_id: str, input: str, expected: str, **options) -> TaskPackView: ...
    def task_pack_holdout(self, pack_id: str) -> tuple[tuple[str, str], ...]: ...


@runtime_checkable
class TaskPackService(Protocol):
    """Optional injected material capability, independent of search enablement."""
    def task_packs(self) -> tuple[TaskPackView, ...]: ...
    def save_training_task(self, pack_id: str, input: str, expected: str, **options) -> TaskPackView: ...
    def task_pack_holdout(self, pack_id: str) -> tuple[tuple[str, str], ...]: ...


def format_optimization_activity(activity: OptimizationActivity) -> str:
    """Show one batch's progress separately from request budget consumption."""
    text = activity.phase
    if activity.total > 0:
        filled = max(0, min(10, 10 * activity.completed // activity.total))
        text += f" [{'#' * filled}{'-' * (10 - filled)}] {activity.completed}/{activity.total}"
    if activity.model_limit:
        text += f" · model calls {activity.model_calls}/{activity.model_limit}"
    if activity.trial_limit:
        text += f" · trials used {activity.trial_calls}/{activity.trial_limit}"
    if activity.failed_trials:
        text += f" · failed trials {activity.failed_trials}"
    if activity.model_calls:
        if activity.usage_reported_calls:
            text += (f' · reported tokens {activity.input_tokens + activity.output_tokens:,}'
                     f' (in {activity.input_tokens:,} / out {activity.output_tokens:,};'
                     f' usage {activity.usage_reported_calls}/{activity.model_calls} calls)')
        else:
            text += ' · tokens unknown (Provider usage not yet reported)'
    return text
