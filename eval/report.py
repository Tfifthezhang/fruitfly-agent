"""Task outcomes, runtime records, and JSON/Markdown benchmark reports."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
import math
from typing import Any, Mapping
from .contracts import EvaluationRequest, SCHEMA_VERSION


@dataclass(frozen=True)
class MetricRecord:
    name: str
    value: float | int | None
    unit: str
    aggregation: str
    sample_count: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MetricRecord:
        name, value = data.get("name"), data.get("value")
        if not isinstance(name, str) or not name:
            raise ValueError("metric.name must be a non-empty string")
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise ValueError("metric.value must be finite numeric data or null")
        samples = data.get("sample_count", 0)
        if type(samples) is not int or samples < 0:
            raise ValueError("metric.sample_count must be a non-negative integer")
        return cls(name, value, str(data.get("unit", "ratio")), str(data.get("aggregation", "mean")), samples)


@dataclass(frozen=True)
class EvaluationReport:
    evaluation_id: str
    status: str
    started_at: str
    completed_at: str
    benchmark: Mapping[str, Any]
    runtime: Mapping[str, Any]
    execution: Mapping[str, Any]
    metrics: tuple[MetricRecord, ...] = ()
    errors: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[Mapping[str, Any], ...] = ()
    readiness: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, **asdict(self)}

    def render_markdown(self) -> str:
        resolved = self.runtime.get("resolved", self.runtime)
        lines = [f"# Evaluation {self.evaluation_id}", "", "## Summary", "",
                 f"- Status: `{self.status}`",
                 f"- Benchmark: `{self.benchmark.get('benchmark')}` / `{self.benchmark.get('variant')}`",
                 f"- Started: `{self.started_at}`", f"- Completed: `{self.completed_at}`",
                 "", "## Configuration", "",
                 f"- Config: `{resolved.get('config_path')}`", f"- Profile: `{resolved.get('profile')}`",
                 f"- Execution policy: `{resolved.get('execution_policy', 'see task runtime manifests')}`",
                 "- Actual per-task runtime manifests, when available: `trials/`",
                 "- Selected runtime files and logs: `artifacts/`", "", "## Results", ""]
        if self.metrics:
            lines += ["| Metric | Value | Unit | Samples |", "|---|---:|---|---:|"]
            for metric in self.metrics:
                value = "—" if metric.value is None else str(metric.value)
                lines.append(f"| {metric.name} | {value} | {metric.unit} | {metric.sample_count} |")
        else:
            lines.append("No benchmark metrics were produced.")
        lines += ["", "## Execution Readiness", "",
                  f"- Trials with execution evidence: {self.readiness.get('observed', 0)}",
                  f"- Completed execution paths: {self.readiness.get('completed', 0)}",
                  f"- Execution errors: {self.readiness.get('errors', 0)}",
                  "- A zero reward can have a completed execution path.",
                  "", "## Task Results", "", "See `trials/` for task outcomes, phase evidence and runtime metadata.", "", "## Failures", ""]
        if self.errors:
            for key, value in self.errors.items():
                if key == "trials" and isinstance(value, list):
                    for item in value:
                        lines.append(f"- Trial `{item['task_id']}`: {item['type']} (see `{item['path']}`)")
                else:
                    lines.append(f"- {key}: {value}")
        else:
            lines.append("None.")
        lines += ["", "## Artifacts", "", "- Request and execution options: `request.json`"]
        lines.extend(f"- `{item.get('path')}` ({item.get('kind', 'artifact')})" for item in self.artifacts)
        return "\n".join(lines) + "\n"


def report_from_runner_result(
    request: EvaluationRequest, result: Mapping[str, Any], *, evaluation_id: str,
    benchmark: Mapping[str, Any], started_at: str, completed_at: str,
) -> EvaluationReport:
    metrics, errors, artifacts, trials = (result.get(key, default) for key, default in
        (("metrics", []), ("errors", {}), ("artifacts", []), ("trials", [])))
    if not isinstance(metrics, list) or not all(isinstance(item, Mapping) for item in metrics):
        raise ValueError("runner result metrics must be a list of objects")
    if not isinstance(errors, Mapping) or not isinstance(artifacts, list) or not isinstance(trials, list):
        raise ValueError("runner result errors/artifacts/trials have invalid shapes")
    reported_errors = dict(errors)
    trial_errors = []
    for index, trial in enumerate(trials):
        if not isinstance(trial, Mapping) or trial.get("status") != "error":
            continue
        detail = trial.get("error")
        trial_errors.append({"task_id": str(trial.get("task_id", "unknown")),
            "type": str(detail.get("type", "TrialError")) if isinstance(detail, Mapping) else "TrialError",
            "path": f"trials/{index:06d}.json"})
    if trial_errors:
        reported_errors["trials"] = trial_errors
    status = str(result.get("status", "completed"))
    if status not in {"completed", "blocked", "failed"}:
        raise ValueError("unsupported evaluation status")
    runtime = asdict(request.runtime)
    if isinstance(result.get("runtime_snapshot"), Mapping):
        runtime["resolved"] = dict(result["runtime_snapshot"])
    execution_records = [t["execution"] for t in trials if isinstance(t, Mapping) and isinstance(t.get("execution"), Mapping)]
    readiness = {"observed": len(execution_records),
                 "completed": sum(r.get("state") == "completed" for r in execution_records),
                 "errors": sum(r.get("state") == "error" for r in execution_records)}
    return EvaluationReport(evaluation_id, status, started_at, completed_at, benchmark,
        runtime, asdict(request.execution), tuple(MetricRecord.from_dict(item) for item in metrics),
        reported_errors, tuple(dict(item) for item in artifacts if isinstance(item, Mapping)), readiness)


__all__ = ["EvaluationReport", "MetricRecord", "report_from_runner_result"]
