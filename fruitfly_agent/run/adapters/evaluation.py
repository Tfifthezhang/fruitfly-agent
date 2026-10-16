"""Adapt optional Eval task sources to the Application improvement lifecycle."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Mapping, Callable

from fruitfly_agent.interactive import AgentApplication, EvaluationBenchmarkOption, EvaluationSnapshot, EvaluationVariantOption
from .benchmark_trials import BenchmarkTrialClient


class RunEvaluationController:
    """Load the Eval catalog and route confirmed task previews to Application."""

    def __init__(
        self,
        application: AgentApplication,
        *,
        workspace: Path | Callable[[], Path],
        environment: Mapping[str, str] | Callable[[], Mapping[str, str]],
        python_executable: str | None = None,
        improvement_available=None,
        benchmark_preview=None,
    ) -> None:
        self.application = application
        self._workspace = workspace
        self._host_environment = environment
        self.python_executable = python_executable or sys.executable
        self.available_query = improvement_available
        self.preview_benchmark = benchmark_preview
        self.improvement_previews: dict[str, tuple[BenchmarkTrialClient, str]] = {}

    @property
    def improvement_available(self) -> bool:
        return self.available_query is not None and self.available_query()

    def benchmark_preview(self, request, direction=""):
        if not self.improvement_available or self.preview_benchmark is None:
            raise ValueError("no executable search and verification binding is available")
        if self.application.running or self.application.pending_count:
            raise RuntimeError("finish or cancel active work before starting improvement")
        from dataclasses import asdict
        executor = BenchmarkTrialClient(workspace=self.workspace, environment=self.environment,
                                        python_executable=self.python_executable)
        selection = {key: value for key, value in asdict(request).items() if value is not None}
        preview = self.preview_benchmark(selection, executor, direction)
        self.improvement_previews[preview.preview_token] = (
            executor, direction.strip() or "Improve completion of the frozen original benchmark tasks.")
        return preview

    async def improve(self, preview_token, on_event=None):
        try:
            executor, direction = self.improvement_previews.pop(preview_token)
        except KeyError as exc:
            raise ValueError("unknown or consumed improvement preview") from exc
        executor.on_event = on_event
        return await self.application.improve(direction, preview_token=preview_token)

    @property
    def workspace(self) -> Path:
        return self._workspace() if callable(self._workspace) else self._workspace

    @property
    def environment(self) -> Mapping[str, str]:
        return self._host_environment() if callable(self._host_environment) else self._host_environment

    def improvement_snapshot(self) -> EvaluationSnapshot:
        import subprocess

        completed = subprocess.run(
            [self.python_executable, "-m", "eval", "catalog", "--json", "--improvement"],
            cwd=self.workspace,
            check=False,
            capture_output=True,
            text=True,
            env=self._environment(),
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "could not load eval catalog")
        payload = json.loads(completed.stdout)
        benchmarks = []
        for item in payload.get("benchmarks", []):
            variants = []
            for variant in item.get("variants", []):
                preflight = variant.get("preflight", {})
                checks = preflight.get("checks", [])
                failures = tuple(
                    str(check.get("detail", ""))
                    for check in checks
                    if not check.get("ok", False)
                )
                variants.append(
                    EvaluationVariantOption(
                        str(variant["id"]),
                        str(variant["label"]),
                        str(variant["description"]),
                        bool(preflight.get("available", False)),
                        failures,
                    )
                )
            benchmarks.append(
                EvaluationBenchmarkOption(
                    str(item["id"]),
                    str(item["label"]),
                    str(item["description"]),
                    str(item["version"]),
                    tuple(variants),
                )
            )
        return EvaluationSnapshot(benchmarks=tuple(benchmarks))

    def _environment(self) -> dict[str, str]:
        environment = {**os.environ, **self.environment}
        source_root = str(Path(__file__).resolve().parents[3])
        existing = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            source_root if not existing else os.pathsep.join((source_root, existing))
        )
        return environment

__all__ = ["RunEvaluationController"]
