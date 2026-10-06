"""Stable machine-readable and Markdown evaluation reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .contracts import EvaluationPlan, SCHEMA_VERSION


@dataclass(frozen=True)
class MetricRecord:
    name: str
    value: float | int | None
    unit: str
    direction: str
    scope: str
    condition_id: str
    aggregation: str
    sample_count: int
    confidence_interval: tuple[float, float] | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MetricRecord":
        name = data.get("name")
        condition = data.get("condition_id")
        if not isinstance(name, str) or not name:
            raise ValueError("metric.name must be a non-empty string")
        if not isinstance(condition, str) or not condition:
            raise ValueError("metric.condition_id must be a non-empty string")
        value = data.get("value")
        if value is not None and not isinstance(value, (int, float)):
            raise ValueError("metric.value must be numeric or null")
        interval = data.get("confidence_interval")
        if interval is not None:
            if not isinstance(interval, list) or len(interval) != 2:
                raise ValueError("metric.confidence_interval must contain two values")
            confidence_interval = (float(interval[0]), float(interval[1]))
        else:
            confidence_interval = None
        return cls(
            name=name,
            value=value,
            unit=str(data.get("unit", "ratio")),
            direction=str(data.get("direction", "higher_is_better")),
            scope=str(data.get("scope", "benchmark")),
            condition_id=condition,
            aggregation=str(data.get("aggregation", "mean")),
            sample_count=int(data.get("sample_count", 0)),
            confidence_interval=confidence_interval,
        )


@dataclass(frozen=True)
class EvaluationReport:
    evaluation_id: str
    status: str
    mode: str
    started_at: str
    completed_at: str
    benchmark: Mapping[str, Any]
    runtime: Mapping[str, Any]
    execution: Mapping[str, Any]
    conditions: tuple[Mapping[str, Any], ...]
    metrics: tuple[MetricRecord, ...] = ()
    comparisons: tuple[Mapping[str, Any], ...] = ()
    errors: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "evaluation_id": self.evaluation_id,
            "status": self.status,
            "mode": self.mode,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "benchmark": dict(self.benchmark),
            "runtime": dict(self.runtime),
            "execution": dict(self.execution),
            "conditions": [dict(item) for item in self.conditions],
            "metrics": [asdict(item) for item in self.metrics],
            "comparisons": [dict(item) for item in self.comparisons],
            "errors": dict(self.errors),
            "artifacts": [dict(item) for item in self.artifacts],
        }

    def render_markdown(self) -> str:
        lines = [
            f"# Evaluation {self.evaluation_id}",
            "",
            "## Summary",
            "",
            f"- Status: `{self.status}`",
            f"- Mode: `{self.mode}`",
            f"- Benchmark: `{self.benchmark.get('benchmark')}` / "
            f"`{self.benchmark.get('variant')}` resource profile",
        ]
        trial_errors = self.errors.get("trials")
        if isinstance(trial_errors, list):
            lines.append(f"- Trial errors: {len(trial_errors)} (see Failures)")
        lines.extend(["", "## Experimental Conditions", ""])
        for condition in self.conditions:
            lines.append(
                f"- `{condition.get('condition_id')}`: {condition.get('label', '')}"
            )
        lines.extend(["", "## Primary Results", ""])
        if self.metrics:
            lines.extend(
                [
                    "| Condition | Metric | Value | Unit | Samples |",
                    "|---|---|---:|---|---:|",
                ]
            )
            for metric in self.metrics:
                value = "—" if metric.value is None else str(metric.value)
                lines.append(
                    f"| {metric.condition_id} | {metric.name} | {value} | "
                    f"{metric.unit} | {metric.sample_count} |"
                )
        else:
            lines.append("No benchmark metrics were produced.")
        lines.extend(["", "## Quality, Cost, and Reliability", ""])
        selected = [
            metric
            for metric in self.metrics
            if metric.name in {"latency_ms", "cost_usd", "error_rate", "timeout_rate"}
        ]
        if selected:
            lines.extend(
                f"- {item.condition_id} · {item.name}: {item.value} {item.unit}"
                for item in selected
            )
        else:
            lines.append("No secondary cost or reliability metrics were reported.")
        lines.extend(["", "## Comparison", ""])
        if self.comparisons:
            lines.extend(
                f"- {item.get('metric')}: {item.get('delta')}"
                for item in self.comparisons
            )
        else:
            lines.append("Not applicable or no comparison was produced.")
        lines.extend(["", "## Task Results", "", "See `trials/` for task-level records."])
        lines.extend(["", "## Failures", ""])
        if self.errors:
            for key, value in self.errors.items():
                if key == "trials" and isinstance(value, list):
                    for item in value:
                        if isinstance(item, Mapping):
                            lines.append(
                                f"- Trial `{item.get('task_id')}`: "
                                f"{item.get('type')} (see `{item.get('path')}`)"
                            )
                else:
                    lines.append(f"- {key}: {value}")
        else:
            lines.append("None.")
        lines.extend(
            [
                "",
                "## Reproducibility",
                "",
                f"- Runtime manifest: `{self.runtime.get('manifest_digest', '')}`",
                f"- Started: `{self.started_at}`",
                f"- Completed: `{self.completed_at}`",
                "- Exact request and frozen plan: `request.json`, `plan.json`",
                "",
                "## Artifacts",
                "",
            ]
        )
        if self.artifacts:
            lines.extend(
                f"- `{item.get('path')}` ({item.get('kind', 'artifact')})"
                for item in self.artifacts
            )
        else:
            lines.append("No additional artifacts.")
        return "\n".join(lines) + "\n"


def report_from_runner_result(
    plan: EvaluationPlan,
    result: Mapping[str, Any],
    *,
    started_at: str,
    completed_at: str,
) -> EvaluationReport:
    metrics = result.get("metrics", [])
    comparisons = result.get("comparisons", [])
    errors = result.get("errors", {})
    if not isinstance(metrics, list) or not isinstance(comparisons, list):
        raise ValueError("runner result metrics/comparisons must be lists")
    if not isinstance(errors, Mapping):
        raise ValueError("runner result errors must be an object")
    reported_errors = dict(errors)
    trial_errors = []
    for index, trial in enumerate(result.get("trials", [])):
        if not isinstance(trial, Mapping) or trial.get("status") != "error":
            continue
        detail = trial.get("error")
        trial_errors.append(
            {
                "task_id": str(trial.get("task_id", "unknown")),
                "type": (
                    str(detail.get("type", "TrialError"))
                    if isinstance(detail, Mapping)
                    else "TrialError"
                ),
                "path": f"trials/{index:06d}.json",
            }
        )
    if trial_errors:
        reported_errors["trials"] = trial_errors
    request = plan.request
    runtime = request.get("runtime", {})
    parsed_metrics = tuple(MetricRecord.from_dict(item) for item in metrics)
    condition_ids = {str(item.get("condition_id")) for item in plan.conditions}
    unknown_conditions = {
        item.condition_id for item in parsed_metrics if item.condition_id not in condition_ids
    }
    if unknown_conditions:
        raise ValueError(
            "runner metrics reference unknown conditions: "
            + ", ".join(sorted(unknown_conditions))
        )
    return EvaluationReport(
        evaluation_id=plan.evaluation_id,
        status=str(result.get("status", "completed")),
        mode=str(request.get("mode")),
        started_at=started_at,
        completed_at=completed_at,
        benchmark=plan.benchmark,
        runtime={
            "manifest_digest": plan.reproducibility.get("runtime_manifest_digest"),
            "profile": runtime.get("profile") if isinstance(runtime, Mapping) else None,
        },
        execution=plan.reproducibility,
        conditions=plan.conditions,
        metrics=parsed_metrics,
        comparisons=tuple(dict(item) for item in comparisons if isinstance(item, Mapping)),
        errors=reported_errors,
        artifacts=tuple(
            dict(item)
            for item in result.get("artifacts", [])
            if isinstance(item, Mapping)
        ),
    )


__all__ = ["EvaluationReport", "MetricRecord", "report_from_runner_result"]
