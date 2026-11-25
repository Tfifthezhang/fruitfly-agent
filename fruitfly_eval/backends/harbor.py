"""Existing Harbor preparation exposed through the benchmark-neutral service port."""
from pathlib import Path
from typing import Any

from fruitfly_eval.benchmarks.base import BenchmarkDescriptor, ProgressSink
from fruitfly_eval.contracts import EvaluationRequest
from fruitfly_eval.harbor.host import HostConfig


class HarborPreparation:
    def read_host(self, workspace: Path, path: str | Path | None) -> HostConfig:
        host = HostConfig.read(workspace, path)
        if getattr(host, 'backend_file', None) is not None:
            raise ValueError('the built-in Harbor backend does not consume a backend document')
        return host

    def prepare(self, request: EvaluationRequest, descriptor: BenchmarkDescriptor, host: Any,
                *, package: Path | None, tasks_only: bool, progress: ProgressSink | None) -> dict[str, Any]:
        from fruitfly_eval.harbor.preparation import prepare
        return prepare(request, descriptor, host, package=package, tasks_only=tasks_only, progress=progress)

    def inspect(self, request: EvaluationRequest, descriptor: BenchmarkDescriptor, host: Any,
                *, receipt: dict[str, Any] | None = None) -> dict[str, Any]:
        from fruitfly_eval.harbor.preparation import inspect
        return inspect(request, descriptor, host, receipt=receipt) if receipt is not None else inspect(request, descriptor, host)

    def load(self, host: Any, descriptor: BenchmarkDescriptor, variant: str) -> dict[str, Any]:
        from fruitfly_eval.harbor.preparation import load_preparation
        return load_preparation(host, descriptor, variant)
