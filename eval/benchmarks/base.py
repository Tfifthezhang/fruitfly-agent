"""Descriptors and the benchmark-runner boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


ProgressSink = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class BenchmarkVariant:
    variant_id: str
    label: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.variant_id,
            "label": self.label,
            "description": self.description,
        }


@dataclass(frozen=True)
class BenchmarkDescriptor:
    benchmark_id: str
    label: str
    description: str
    version: str
    adapter_version: str
    variants: tuple[BenchmarkVariant, ...]
    metric_names: tuple[str, ...]
    dataset: str
    network: Mapping[str, bool]
    isolation: str
    smoke_task: str | None = None


@dataclass(frozen=True)
class PreflightResult:
    available: bool
    checks: tuple[Mapping[str, Any], ...]
    command: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "checks": [dict(item) for item in self.checks],
        }


class BenchmarkAdapter(Protocol):
    descriptor: BenchmarkDescriptor

    def preflight(self, variant: str) -> PreflightResult: ...

    def run(
        self, *, plan_path: Path, result_path: Path, variant: str,
        progress: ProgressSink | None = None,
    ) -> None: ...


__all__ = [
    "BenchmarkAdapter",
    "BenchmarkDescriptor",
    "BenchmarkVariant",
    "PreflightResult",
]
