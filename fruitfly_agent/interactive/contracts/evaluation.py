"""Renderer-neutral benchmark task selection and improvement capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Protocol, runtime_checkable
from .improvement import ImprovementPreview
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
    generator_id: str = 'agent-editor-v1'
    component_ids: tuple[str, ...] = ()
    mode: str = 'parallel'
    width: int = 1
    depth: int = 1
    max_model_calls: int = 128
    max_executions: int = 64

    def __post_init__(self):
        if type(self.task_limit) is not int or not 1 <= self.task_limit <= 12:
            raise ValueError("improvement task limit must be 1–12")


@runtime_checkable
class BenchmarkImprovementController(Protocol):
    @property
    def improvement_available(self) -> bool: ...
    def improvement_snapshot(self) -> EvaluationSnapshot: ...
    def benchmark_preview(self, request: BenchmarkImprovementRequest, direction: str = "") -> ImprovementPreview: ...
    async def improve(self, preview_token: str, on_event: EvaluationEventSink | None = None) -> tuple[CandidateView, ...]: ...


__all__ = [
    "EvaluationBenchmarkOption",
    "EvaluationEventSink",
    "EvaluationSnapshot",
    "EvaluationVariantOption",
    "BenchmarkImprovementRequest",
    "BenchmarkImprovementController",
]
