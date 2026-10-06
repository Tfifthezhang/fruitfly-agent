"""Execute frozen plans through benchmark-owned isolated runners."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Mapping

from .benchmarks.base import ProgressSink
from .catalog import BenchmarkCatalog, builtin_catalog
from .contracts import EvaluationPlan, EvaluationRequest, TrialRecord
from .report import EvaluationReport, report_from_runner_result
from .storage import EvaluationStore


def execute_plan(
    plan: EvaluationPlan,
    *,
    output_root: Path,
    catalog: BenchmarkCatalog | None = None,
    progress: ProgressSink | None = None,
) -> tuple[EvaluationReport, EvaluationStore]:
    benchmarks = catalog or builtin_catalog()
    adapter = benchmarks.get(str(plan.benchmark["benchmark"]))
    variant = str(plan.benchmark["variant"])
    store = EvaluationStore(output_root, plan.evaluation_id)
    store.create()
    store.write_json("request.json", dict(plan.request))
    plan_path = store.write_json("plan.json", plan.to_dict())
    started_at = _timestamp()
    result_path = store.artifacts / "runner-result.json"
    preflight = adapter.preflight(variant)
    if progress is not None:
        progress({"type": "preflight", "available": preflight.available})
    if not preflight.available:
        result: Mapping[str, Any] = {
            "status": "blocked",
            "metrics": [],
            "comparisons": [],
            "errors": {"preflight": [dict(item) for item in preflight.checks]},
            "artifacts": [],
        }
    else:
        try:
            adapter.run(
                plan_path=plan_path, result_path=result_path,
                variant=variant, progress=progress,
            )
            loaded = json.loads(result_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, Mapping):
                raise ValueError("runner result must be a JSON object")
            if loaded.get("schema_version") != 1:
                raise ValueError("unsupported runner result schema_version")
            result = loaded
            trials = loaded.get("trials", [])
            if not isinstance(trials, list):
                raise ValueError("runner result trials must be a list")
            condition_ids = {
                str(item.get("condition_id")) for item in plan.conditions
            }
            for index, trial in enumerate(trials):
                if not isinstance(trial, Mapping):
                    raise ValueError("runner trial must be an object")
                record = TrialRecord.from_dict(trial)
                if record.condition_id not in condition_ids:
                    raise ValueError(
                        f"trial references unknown condition {record.condition_id!r}"
                    )
                store.write_json(f"trials/{index:06d}.json", record.to_dict())
        except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            result = {
                "status": "failed",
                "metrics": [],
                "comparisons": [],
                "errors": {"runner": str(exc)},
                "artifacts": [],
            }
    try:
        report = report_from_runner_result(
            plan,
            result,
            started_at=started_at,
            completed_at=_timestamp(),
        )
    except (TypeError, ValueError) as exc:
        report = report_from_runner_result(
            plan,
            {
                "status": "failed",
                "metrics": [],
                "comparisons": [],
                "errors": {"result_validation": str(exc)},
                "artifacts": [],
            },
            started_at=started_at,
            completed_at=_timestamp(),
        )
    store.write_json("report.json", report.to_dict())
    store.write_text("report.md", report.render_markdown())
    if progress is not None:
        progress({"type": "report_written", "status": report.status})
    return report, store


def execute_request(
    request: EvaluationRequest,
    *,
    output_root: Path,
    catalog: BenchmarkCatalog | None = None,
) -> tuple[EvaluationReport, EvaluationStore]:
    from .planning import create_plan

    plan = create_plan(request, catalog=catalog)
    return execute_plan(plan, output_root=output_root, catalog=catalog)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


__all__ = ["execute_plan", "execute_request"]
