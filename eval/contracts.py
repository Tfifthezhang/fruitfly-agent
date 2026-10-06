"""Versioned, JSON-safe contracts shared by the eval CLI and external runners."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = 1
EVALUATION_MODES = ("current_setup", "mechanism_comparison")


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class RuntimeReference:
    """Non-secret pointer to the runtime being evaluated."""

    manifest: Mapping[str, Any]
    config_path: str
    profile: str
    working_directory: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RuntimeReference":
        manifest = data.get("manifest")
        if not isinstance(manifest, Mapping):
            raise ValueError("runtime.manifest must be an object")
        return cls(
            manifest=dict(manifest),
            config_path=_require_text(data.get("config_path"), "runtime.config_path"),
            profile=_require_text(data.get("profile"), "runtime.profile"),
            working_directory=_require_text(
                data.get("working_directory"), "runtime.working_directory"
            ),
        )


@dataclass(frozen=True)
class BenchmarkSelection:
    benchmark_id: str
    variant: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkSelection":
        return cls(
            benchmark_id=_require_text(data.get("id"), "benchmark.id"),
            variant=_require_text(data.get("variant"), "benchmark.variant"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.benchmark_id, "variant": self.variant}


@dataclass(frozen=True)
class ComparisonSelection:
    mechanism_id: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ComparisonSelection":
        return cls(
            mechanism_id=_require_text(
                data.get("mechanism_id"), "comparison.mechanism_id"
            )
        )


@dataclass(frozen=True)
class ExecutionOptions:
    attempts: int = 1
    concurrency: int = 1
    seed: int = 0
    timeout_seconds: int = 3600

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionOptions":
        options = cls(
            attempts=data.get("attempts", 1),
            concurrency=data.get("concurrency", 1),
            seed=data.get("seed", 0),
            timeout_seconds=data.get("timeout_seconds", 3600),
        )
        if not isinstance(options.attempts, int) or options.attempts < 1:
            raise ValueError("execution.attempts must be at least 1")
        if not isinstance(options.concurrency, int) or options.concurrency < 1:
            raise ValueError("execution.concurrency must be at least 1")
        if not isinstance(options.seed, int):
            raise ValueError("execution.seed must be an integer")
        if not isinstance(options.timeout_seconds, int) or options.timeout_seconds < 1:
            raise ValueError("execution.timeout_seconds must be at least 1")
        return options


@dataclass(frozen=True)
class EvaluationRequest:
    schema_version: int
    mode: str
    runtime: RuntimeReference
    benchmark: BenchmarkSelection
    comparison: ComparisonSelection | None = None
    execution: ExecutionOptions = field(default_factory=ExecutionOptions)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvaluationRequest":
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported evaluation request schema_version: {version!r}"
            )
        mode = data.get("mode")
        if mode not in EVALUATION_MODES:
            raise ValueError(f"unsupported evaluation mode: {mode!r}")
        runtime = data.get("runtime")
        benchmark = data.get("benchmark")
        execution = data.get("execution", {})
        if not isinstance(runtime, Mapping):
            raise ValueError("runtime must be an object")
        if not isinstance(benchmark, Mapping):
            raise ValueError("benchmark must be an object")
        if not isinstance(execution, Mapping):
            raise ValueError("execution must be an object")
        raw_comparison = data.get("comparison")
        if mode == "mechanism_comparison":
            if not isinstance(raw_comparison, Mapping):
                raise ValueError("comparison is required for mechanism_comparison")
            comparison = ComparisonSelection.from_dict(raw_comparison)
        else:
            if raw_comparison is not None:
                raise ValueError("comparison must be null for current_setup")
            comparison = None
        return cls(
            schema_version=version,
            mode=mode,
            runtime=RuntimeReference.from_dict(runtime),
            benchmark=BenchmarkSelection.from_dict(benchmark),
            comparison=comparison,
            execution=ExecutionOptions.from_dict(execution),
        )

    @classmethod
    def read(cls, path: str | Path) -> "EvaluationRequest":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise ValueError("evaluation request must be a JSON object")
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "runtime": asdict(self.runtime),
            "benchmark": self.benchmark.to_dict(),
            "comparison": asdict(self.comparison) if self.comparison else None,
            "execution": asdict(self.execution),
        }


@dataclass(frozen=True)
class EvaluationPlan:
    schema_version: int
    evaluation_id: str
    request: Mapping[str, Any]
    benchmark: Mapping[str, Any]
    conditions: tuple[Mapping[str, Any], ...]
    runner: Mapping[str, Any]
    network: Mapping[str, bool]
    reproducibility: Mapping[str, Any]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvaluationPlan":
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported evaluation plan schema_version")
        fields = ("request", "benchmark", "runner", "network", "reproducibility")
        if any(not isinstance(data.get(name), Mapping) for name in fields):
            raise ValueError("evaluation plan contains a malformed object field")
        conditions = data.get("conditions")
        if not isinstance(conditions, list) or not all(
            isinstance(item, Mapping) for item in conditions
        ):
            raise ValueError("evaluation plan conditions must be a list of objects")
        return cls(
            schema_version=SCHEMA_VERSION,
            evaluation_id=_require_text(data.get("evaluation_id"), "evaluation_id"),
            request=dict(data["request"]),
            benchmark=dict(data["benchmark"]),
            conditions=tuple(dict(item) for item in conditions),
            runner=dict(data["runner"]),
            network={str(key): bool(value) for key, value in data["network"].items()},
            reproducibility=dict(data["reproducibility"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evaluation_id": self.evaluation_id,
            "request": dict(self.request),
            "benchmark": dict(self.benchmark),
            "conditions": [dict(item) for item in self.conditions],
            "runner": dict(self.runner),
            "network": dict(self.network),
            "reproducibility": dict(self.reproducibility),
        }


@dataclass(frozen=True)
class TrialRecord:
    trial_id: str
    condition_id: str
    task_id: str
    status: str
    metrics: tuple[Mapping[str, Any], ...] = ()
    error: Mapping[str, Any] | None = None
    phase: str = "evaluation"
    sequence_index: int = 0
    harness_revision: str = "H0"
    parent_harness_revision: str | None = None
    state_policy: str = "clean"
    artifact_lineage: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TrialRecord":
        metrics = data.get("metrics", [])
        lineage = data.get("artifact_lineage", [])
        if not isinstance(metrics, list) or not all(
            isinstance(item, Mapping) for item in metrics
        ):
            raise ValueError("trial.metrics must be a list of objects")
        if not isinstance(lineage, list) or not all(
            isinstance(item, str) for item in lineage
        ):
            raise ValueError("trial.artifact_lineage must be a list of strings")
        error = data.get("error")
        if error is not None and not isinstance(error, Mapping):
            raise ValueError("trial.error must be an object or null")
        return cls(
            trial_id=_require_text(data.get("trial_id"), "trial.trial_id"),
            condition_id=_require_text(
                data.get("condition_id"), "trial.condition_id"
            ),
            task_id=_require_text(data.get("task_id"), "trial.task_id"),
            status=_require_text(data.get("status"), "trial.status"),
            metrics=tuple(dict(item) for item in metrics),
            error=dict(error) if error is not None else None,
            phase=str(data.get("phase", "evaluation")),
            sequence_index=int(data.get("sequence_index", 0)),
            harness_revision=str(data.get("harness_revision", "H0")),
            parent_harness_revision=(
                str(data["parent_harness_revision"])
                if data.get("parent_harness_revision") is not None
                else None
            ),
            state_policy=str(data.get("state_policy", "clean")),
            artifact_lineage=tuple(lineage),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "SCHEMA_VERSION",
    "EVALUATION_MODES",
    "BenchmarkSelection",
    "ComparisonSelection",
    "EvaluationPlan",
    "EvaluationRequest",
    "ExecutionOptions",
    "RuntimeReference",
    "TrialRecord",
]
