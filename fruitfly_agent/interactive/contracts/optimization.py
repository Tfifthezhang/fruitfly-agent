"""Optimization execution contracts and frontend views."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable
from fruitfly_agent.interactive.contracts.candidates import CandidateView


@dataclass(frozen=True)
class OptimizationPreview:
    algorithm: str
    label: str
    cost_notice: str
    details: tuple[tuple[str, str], ...] = ()
    target: str = ''
    preview_token: str = ''


class OptimizationService(Protocol):
    def optimization_preview(self, manifest: Mapping[str, object], *, pack_id=None, direction="") -> OptimizationPreview: ...
    async def optimize(self, manifest: Mapping[str, object], direction: str, *, preview_token="") -> tuple[CandidateView, ...]: ...
    def cancel_optimization(self) -> bool: ...


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


