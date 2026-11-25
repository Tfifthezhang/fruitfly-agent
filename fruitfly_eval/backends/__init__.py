"""Injected execution services; benchmark discovery stays in the existing Catalog."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from fruitfly_eval.benchmarks.base import BenchmarkDescriptor, ProgressSink
from fruitfly_eval.contracts import EvaluationRequest


@runtime_checkable
class PreparationBackend(Protocol):
    """Prepare owned material without model inference and inspect its identity."""
    def read_host(self, workspace: Path, path: str | Path | None) -> Any: ...
    def prepare(self, request: EvaluationRequest, descriptor: BenchmarkDescriptor, host: Any,
                *, package: Path | None, tasks_only: bool, progress: ProgressSink | None) -> dict[str, Any]: ...
    def inspect(self, request: EvaluationRequest, descriptor: BenchmarkDescriptor, host: Any,
                *, receipt: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def load(self, host: Any, descriptor: BenchmarkDescriptor, variant: str) -> dict[str, Any]: ...


@runtime_checkable
class HostConfigured(Protocol):
    def configure_host(self, path: str) -> None: ...


@runtime_checkable
class WorkspaceInputs(Protocol):
    def initial_files(self) -> dict[str, str]: ...


def preparation_backend(adapter: Any) -> PreparationBackend:
    backend = getattr(adapter, 'preparation', None)
    if not isinstance(backend, PreparationBackend):
        raise ValueError('benchmark does not provide preparation capabilities')
    return backend
