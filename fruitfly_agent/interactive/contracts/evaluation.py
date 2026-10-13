"""Renderer-neutral values for launching optional external evaluations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Protocol


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
class EvaluationLaunchRequest:
    benchmark_id: str
    variant: str


@dataclass(frozen=True)
class EvaluationLaunchResult:
    status: str
    evaluation_id: str
    report_markdown: str
    report_json: str
    detail: str = ""


class EvaluationController(Protocol):
    def snapshot(self) -> EvaluationSnapshot: ...

    async def run(
        self, request: EvaluationLaunchRequest,
        on_event: EvaluationEventSink | None = None,
    ) -> EvaluationLaunchResult: ...


__all__ = [
    "EvaluationBenchmarkOption",
    "EvaluationController",
    "EvaluationEventSink",
    "EvaluationLaunchRequest",
    "EvaluationLaunchResult",
    "EvaluationSnapshot",
    "EvaluationVariantOption",
]
