"""Run one selected configuration and persist its task results and report."""
from __future__ import annotations
from datetime import UTC, datetime
from pathlib import Path
import json
import uuid
from typing import Any, Mapping
from .benchmarks.base import ProgressSink
from .catalog import BenchmarkCatalog, builtin_catalog
from .contracts import EvaluationRequest, TrialRecord, SCHEMA_VERSION
from .report import EvaluationReport, report_from_runner_result
from .storage import EvaluationStore


def execute_request(
    request: EvaluationRequest, *, output_root: Path, catalog: BenchmarkCatalog | None = None,
    progress: ProgressSink | None = None,
) -> tuple[EvaluationReport, EvaluationStore]:
    # Validate constructed requests as well as JSON requests before external effects.
    request = EvaluationRequest.from_dict(request.to_dict())
    adapter = (catalog or builtin_catalog()).get(request.benchmark.benchmark_id)
    descriptor = adapter.descriptor
    variant = request.benchmark.variant
    if variant not in {item.variant_id for item in descriptor.variants}:
        raise ValueError(f"unknown {descriptor.benchmark_id} variant: {variant}")
    evaluation_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    store = EvaluationStore(output_root, evaluation_id)
    store.create()
    request_path = store.write_json("request.json", request.to_dict())
    started_at = _timestamp()
    result_path = store.artifacts / "runner-result.json"
    if progress is not None:
        progress({"type": "started", "evaluation_id": evaluation_id})
    try:
        preflight = adapter.preflight(variant)
        if progress is not None:
            progress({"type": "preflight", "available": preflight.available})
        if not preflight.available:
            result: Mapping[str, Any] = {"status": "blocked", "errors": {"preflight": [dict(c) for c in preflight.checks]}}
        else:
            adapter.run(request_path=request_path, result_path=result_path, variant=variant, progress=progress)
            loaded = json.loads(result_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, Mapping) or loaded.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("unsupported runner result schema_version")
            trials = loaded.get("trials", [])
            if not isinstance(trials, list):
                raise ValueError("runner result trials must be a list")
            for index, trial in enumerate(trials):
                if not isinstance(trial, Mapping):
                    raise ValueError("runner trial must be an object")
                store.write_json(f"trials/{index:06d}.json", TrialRecord.from_dict(trial).to_dict())
            result = loaded
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        result = {"status": "failed", "errors": {"runner": str(exc)}}
    benchmark = {"benchmark": descriptor.benchmark_id, "version": descriptor.version,
                 "variant": variant, "adapter_version": descriptor.adapter_version, "dataset": descriptor.dataset}
    try:
        report = report_from_runner_result(request, result, evaluation_id=evaluation_id, benchmark=benchmark,
                                          started_at=started_at, completed_at=_timestamp())
    except (TypeError, ValueError) as exc:
        report = report_from_runner_result(request, {"status": "failed", "errors": {"result_validation": str(exc)}},
            evaluation_id=evaluation_id, benchmark=benchmark, started_at=started_at, completed_at=_timestamp())
    store.write_json("report.json", report.to_dict())
    store.write_text("report.md", report.render_markdown())
    if progress is not None:
        progress({"type": "report_written", "status": report.status, "evaluation_id": evaluation_id})
    return report, store


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


__all__ = ["execute_request"]
