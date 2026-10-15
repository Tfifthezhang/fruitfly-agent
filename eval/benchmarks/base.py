"""Descriptors and the benchmark-runner boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Protocol


ProgressSink = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class BenchmarkVariant:
    variant_id: str
    label: str
    description: str
    task_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_names", tuple(self.task_names))
        if (any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]*", name)
                or ".." in name for name in self.task_names)
                or len(set(self.task_names)) != len(self.task_names)):
            raise ValueError("variant task names must be distinct exact registry names")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.variant_id,
            "label": self.label,
            "description": self.description,
        }
        if self.task_names:
            result["task_names"] = list(self.task_names)
        return result


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
        self, *, request_path: Path, result_path: Path, variant: str,
        progress: ProgressSink | None = None,
    ) -> None: ...


__all__ = [
    "BenchmarkAdapter",
    "BenchmarkDescriptor",
    "BenchmarkVariant",
    "PreflightResult",
]
