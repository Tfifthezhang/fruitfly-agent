"""Freeze an evaluation request into a reproducible execution plan."""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

from .catalog import BenchmarkCatalog, builtin_catalog
from .contracts import EvaluationPlan, EvaluationRequest, SCHEMA_VERSION
from .studies import builtin_studies


def create_plan(
    request: EvaluationRequest,
    *,
    catalog: BenchmarkCatalog | None = None,
    now: datetime | None = None,
) -> EvaluationPlan:
    benchmarks = catalog or builtin_catalog()
    adapter = benchmarks.get(request.benchmark.benchmark_id)
    descriptor = adapter.descriptor
    variants = {item.variant_id for item in descriptor.variants}
    if request.benchmark.variant not in variants:
        raise ValueError(
            f"unknown {descriptor.benchmark_id} variant: {request.benchmark.variant}"
        )

    manifest = request.runtime.manifest
    manifest_digest = manifest.get("digest")
    if not isinstance(manifest_digest, str) or not manifest_digest:
        raise ValueError("runtime manifest has no digest")
    components = manifest.get("components")
    if not isinstance(components, list):
        raise ValueError("runtime manifest components must be a list")

    conditions = builtin_studies()[request.mode].conditions(request)

    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    evaluation_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"
    task_identity = {
        "benchmark": descriptor.benchmark_id,
        "version": descriptor.version,
        "variant": request.benchmark.variant,
        "adapter_version": descriptor.adapter_version,
        "smoke_task": (
            descriptor.smoke_task
            if request.benchmark.variant == "smoke"
            else None
        ),
    }
    return EvaluationPlan(
        schema_version=SCHEMA_VERSION,
        evaluation_id=evaluation_id,
        request=request.to_dict(),
        benchmark={
            **task_identity,
            "task_manifest_digest": _stable_digest(task_identity),
            "metric_names": list(descriptor.metric_names),
        },
        conditions=conditions,
        runner={
            "kind": "harbor",
            "protocol_version": 1,
            "isolation": descriptor.isolation,
            "dataset": descriptor.dataset,
            "agent": "eval.harbor_agent:FruitFlyHarborAgent",
            "native_harness_preserved": True,
        },
        network=dict(descriptor.network),
        reproducibility={
            "runtime_manifest_digest": manifest_digest,
            "attempts": request.execution.attempts,
            "concurrency": request.execution.concurrency,
            "seed": request.execution.seed,
            "timeout_seconds": request.execution.timeout_seconds,
            "task_order": (
                "fixed_declared_smoke_task"
                if request.benchmark.variant == "smoke"
                else "official_dataset_order"
            ),
            "resource_profile": request.benchmark.variant,
            "state_policy": "clean_per_trial",
            "secret_values_persisted": False,
        },
    )


def _stable_digest(value: object) -> str:
    import hashlib
    import json

    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


__all__ = ["create_plan"]
