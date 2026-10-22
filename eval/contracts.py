"""Single-configuration evaluation requests and task results."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 2


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _fields(data: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unsupported {name} fields: " + ", ".join(sorted(unknown)))


@dataclass(frozen=True)
class RuntimeReference:
    config_path: str | None = None
    profile: str | None = None
    working_directory: str = "."

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RuntimeReference:
        _fields(data, {"config_path", "profile", "working_directory"}, "runtime")
        return cls(config_path=_text(data["config_path"], "runtime.config_path") if data.get("config_path") is not None else None,
                   profile=_text(data["profile"], "runtime.profile") if data.get("profile") is not None else None,
                   working_directory=_text(data.get("working_directory", "."), "runtime.working_directory"))


@dataclass(frozen=True)
class BenchmarkSelection:
    benchmark_id: str
    variant: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BenchmarkSelection:
        _fields(data, {"id", "variant"}, "benchmark")
        return cls(_text(data.get("id"), "benchmark.id"), _text(data.get("variant"), "benchmark.variant"))

    def to_dict(self) -> dict[str, str]:
        return {"id": self.benchmark_id, "variant": self.variant}


@dataclass(frozen=True)
class ExecutionOptions:
    attempts: int = 1
    concurrency: int = 1
    timeout_seconds: int = 3600

    def __post_init__(self) -> None:
        for key, value in asdict(self).items():
            if type(value) is not int or value < 1:
                raise ValueError(f"execution.{key} must be a positive integer")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExecutionOptions:
        _fields(data, {"attempts", "concurrency", "timeout_seconds"}, "execution")
        return cls(**data)


@dataclass(frozen=True)
class EvaluationRequest:
    schema_version: int
    runtime: RuntimeReference
    benchmark: BenchmarkSelection
    execution: ExecutionOptions = field(default_factory=ExecutionOptions)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvaluationRequest:
        if type(data.get("schema_version")) is not int or data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("evaluation requests require schema_version 2; experimental requests are unsupported")
        _fields(data, {"schema_version", "runtime", "benchmark", "execution"}, "request")
        values = {}
        for key in ("runtime", "benchmark", "execution"):
            value = data.get(key, {} if key in {"execution", "runtime"} else None)
            if not isinstance(value, Mapping):
                raise ValueError(f"{key} must be an object")
            values[key] = value
        return cls(SCHEMA_VERSION, RuntimeReference.from_dict(values["runtime"]),
                   BenchmarkSelection.from_dict(values["benchmark"]), ExecutionOptions.from_dict(values["execution"]))

    @classmethod
    def read(cls, path: str | Path) -> EvaluationRequest:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise ValueError("evaluation request must be a JSON object")
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "runtime": asdict(self.runtime),
                "benchmark": self.benchmark.to_dict(), "execution": asdict(self.execution)}


@dataclass(frozen=True)
class TrialRecord:
    trial_id: str
    task_id: str
    status: str
    metrics: tuple[Mapping[str, Any], ...] = ()
    error: Mapping[str, Any] | None = None
    runtime: Mapping[str, Any] | None = None
    execution: Mapping[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrialRecord:
        metrics = data.get("metrics", [])
        if not isinstance(metrics, list) or not all(isinstance(item, Mapping) for item in metrics):
            raise ValueError("trial.metrics must be a list of objects")
        for key in ("error", "runtime", "execution"):
            if data.get(key) is not None and not isinstance(data[key], Mapping):
                raise ValueError(f"trial.{key} must be an object or null")
        status = _text(data.get("status"), "trial.status")
        if status not in {"passed", "failed", "error"}:
            raise ValueError("invalid trial.status")
        return cls(_text(data.get("trial_id"), "trial.trial_id"), _text(data.get("task_id"), "trial.task_id"),
                   status, tuple(dict(item) for item in metrics), data.get("error"), data.get("runtime"), data.get("execution"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = ["SCHEMA_VERSION", "BenchmarkSelection", "EvaluationRequest", "ExecutionOptions", "RuntimeReference", "TrialRecord"]
