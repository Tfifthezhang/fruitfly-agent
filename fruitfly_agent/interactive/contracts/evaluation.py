"""Renderer-neutral values for launching optional external evaluations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Protocol


EvaluationEventSink = Callable[[Mapping[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class EvaluationModeOption:
    mode_id: str
    label: str
    description: str


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
class EvaluationMechanismOption:
    mechanism_id: str
    label: str


@dataclass(frozen=True)
class EvaluationSnapshot:
    modes: tuple[EvaluationModeOption, ...]
    benchmarks: tuple[EvaluationBenchmarkOption, ...]
    mechanisms: tuple[EvaluationMechanismOption, ...]


@dataclass(frozen=True)
class EvaluationLaunchRequest:
    mode: str
    benchmark_id: str
    variant: str
    mechanism_id: str | None = None


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
    "EvaluationMechanismOption",
    "EvaluationModeOption",
    "EvaluationSnapshot",
    "EvaluationVariantOption",
]
