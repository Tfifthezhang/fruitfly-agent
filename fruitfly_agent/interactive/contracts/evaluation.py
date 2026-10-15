"""Renderer-neutral benchmark task selection and improvement capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Protocol, runtime_checkable
from .optimization import OptimizationPreview
from .candidates import CandidateView


EvaluationEventSink = Callable[[Mapping[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class EvaluationVariantOption:
    variant_id: str
    label: str
    description: str
    available: bool
    preflight: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationBenchmarkOption:
    benchmark_id: str
    label: str
    description: str
    version: str
    variants: tuple[EvaluationVariantOption, ...]


@dataclass(frozen=True)
class EvaluationSnapshot:
    benchmarks: tuple[EvaluationBenchmarkOption, ...]


@dataclass(frozen=True)
class BenchmarkImprovementRequest:
    benchmark_id: str
    variant: str
    task_limit: int = 5

    def __post_init__(self):
        if type(self.task_limit) is not int or not 3 <= self.task_limit <= 12:
            raise ValueError("improvement task limit must be 3–12")


@runtime_checkable
class BenchmarkImprovementController(Protocol):
    @property
    def improvement_available(self) -> bool: ...
    def improvement_snapshot(self) -> EvaluationSnapshot: ...
    def benchmark_preview(self, request: BenchmarkImprovementRequest, direction: str = "") -> OptimizationPreview: ...
    async def improve(self, preview_token: str, on_event: EvaluationEventSink | None = None) -> tuple[CandidateView, ...]: ...


__all__ = [
    "EvaluationBenchmarkOption",
    "EvaluationEventSink",
    "EvaluationSnapshot",
    "EvaluationVariantOption",
    "BenchmarkImprovementRequest",
    "BenchmarkImprovementController",
]
