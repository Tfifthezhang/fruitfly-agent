"""Prepare and inspect one Harbor selection without invoking a model."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any, Callable

from eval.benchmarks.base import BenchmarkDescriptor
from eval.contracts import EvaluationRequest
from eval.installation import resolve_installation
from .dependencies import check_dependencies, prepare_dependencies
from .controller import environment_snapshot
from .host import HostConfig
from .material import check_material, digest, prepare_material, write_json
from .tasks import check_tasks, preparation_key, prepare_tasks
from .environments import environment_config, environment_key, probe_environment
from .docker import image_identity
from .selection import inspect_images


def receipt_path(host: HostConfig, descriptor: BenchmarkDescriptor, variant: str) -> Path:
    return host.cache / "preparations" / (preparation_key(descriptor, variant) + ".json")


def load_preparation(host: HostConfig, descriptor: BenchmarkDescriptor, variant: str) -> dict[str, Any]:
    path = receipt_path(host, descriptor, variant)
    if not path.is_file():
        raise ValueError(f"this Harbor selection is not prepared; run eval prepare --request <request>; expected {path}")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if (receipt.get("schema_version") != 3 or receipt.get("dataset") != descriptor.dataset
            or receipt.get("variant") != variant):
        raise ValueError("preparation format or dataset/variant differs; run eval prepare again")
    if receipt.get("id") != digest({key: value for key, value in receipt.items() if key != "id"}):
        raise ValueError("preparation record changed; run eval prepare again")
    if not receipt.get("tasks"):
        raise ValueError("prepared task selection is empty")
    selection = receipt.get("selection", {})
    if (selection.get("variant") != variant or selection.get("dataset") != descriptor.dataset
            or selection.get("selected") != [task["id"] for task in receipt["tasks"]]
            or (variant == "no_gpu" and any(t["requirements"]["gpu_requirements"] for t in receipt["tasks"]))):
        raise ValueError("prepared selection differs; run eval prepare again")
    check_material(host, receipt["runtime"])
    check_dependencies(host, receipt["dependencies"])
    check_tasks(receipt["tasks"])
    keys = {environment_key(task) for task in receipt["tasks"]}
    if keys != {probe["environment_key"] for probe in receipt["environments"]}:
        raise ValueError("prepared environment probes do not cover the selected tasks")
    return receipt


def prepare(request: EvaluationRequest, descriptor: BenchmarkDescriptor, host: HostConfig,
            *, package: Path | None = None, docker: str = "docker",
            progress: Callable[[dict[str, Any]], None] | None = None,
            tasks_only: bool = False) -> dict[str, Any]:
    def emit(stage: str) -> None:
        if progress:
            progress({"type": "preparation", "stage": stage})
    if not tasks_only:
        package = resolve_installation(str(package) if package else None, checkout=Path(__file__).resolve().parents[2])
    emit("tasks")
    batch = prepare_tasks(host, descriptor, request.benchmark.variant)
    tasks = batch["tasks"]
    inventory = {"selection": batch["selection"], "task_count": len(tasks),
                 "images": inspect_images(tasks, docker),
                 "environments": [{"task_id": t["id"], **t["requirements"]} for t in tasks],
                 "detail": "Task inventory only; runtime, builds, auxiliary Harbor images, verifier and model remain unverified"}
    selection_path = host.cache / "selections" / (preparation_key(descriptor, request.benchmark.variant) + ".json")
    write_json(selection_path, inventory)
    if tasks_only:
        return {"inventory": str(selection_path), **inventory}
    package = package or resolve_installation(None, checkout=Path(__file__).resolve().parents[2])
    emit("runtime")
    runtime = prepare_material(host, package)
    controller = environment_snapshot()
    emit("dependencies")
    dependencies = prepare_dependencies(host, docker)
    emit("environment_probes")
    probes: dict[str, dict[str, Any]] = {}
    for task in tasks:
        key = environment_key(task)
        if key not in probes:
            probes[key] = probe_environment(task, runtime, docker, host.cache / "checks" / key, host=host)
    receipt = {"schema_version": 3, "dataset": descriptor.dataset, "variant": request.benchmark.variant,
               "selection": batch["selection"],
               "controller": controller,
               "runtime": runtime, "dependencies": dependencies, "tasks": tasks,
               "environments": list(probes.values())}
    receipt["id"] = digest(receipt)
    path = receipt_path(host, descriptor, request.benchmark.variant)
    write_json(path, receipt)
    return {"receipt": str(path), "task_count": len(tasks), "runtime_id": runtime["id"],
            "dependencies": dependencies, "selection": batch["selection"], "inventory": str(selection_path)}


def inspect(request: EvaluationRequest, descriptor: BenchmarkDescriptor, host: HostConfig,
            *, docker: str = "docker", receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    try:
        receipt = receipt if receipt is not None else load_preparation(host, descriptor, request.benchmark.variant)
    except (OSError, ValueError, KeyError) as exc:
        return {"available": False, "checks": [{"id": "prepared_material", "status": "failed", "detail": str(exc)}]}
    checks.append({"id": "prepared_material", "status": "passed", "detail": "recorded source, links and dependencies match"})
    controller = environment_snapshot()
    checks.append({"id": "controller_environment", "status": "passed" if controller == receipt["controller"] else "failed",
                   "detail": "controller matches preparation" if controller == receipt["controller"]
                   else "controller Python or installed packages changed; run eval prepare again"})
    checks.append({"id": "controller_dependencies", "status": "passed" if controller["dependency_check"] == "passed" else "unverified",
                   "detail": controller["dependency_check"], "issues": controller["dependency_issues"]})
    for probe in receipt["environments"]:
        for image in probe["images"]:
            try:
                current = image_identity(docker, image["reference"])
                if current != image["id"]:
                    raise ValueError("image tag changed; run eval prepare again")
                checks.append({"id": "image", "image": image["reference"], "image_id": current,
                               "status": "passed", "detail": "cached image matches its prepared runtime probe"})
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                checks.append({"id": "image", "image": image["reference"], "status": "failed", "detail": str(exc)})
    for image, prepared_id in receipt["dependencies"]["images"].items():
        try:
            if image_identity(docker, image) != prepared_id:
                raise ValueError("dependency preparation image changed; run eval prepare again")
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            checks.append({"id": "dependency_image", "image": image, "status": "failed", "detail": str(exc)})
    checks.append({"id": "runtime", "status": "passed",
                   "detail": "prepared Agent imports and verifier dependency probes match unchanged environment identities"})
    checks.append({"id": "verifier_execution", "status": "unverified", "detail": receipt["dependencies"]["verifier_execution"]})
    checks.append({"id": "model_connectivity", "status": "unverified", "detail": "no model requests were made"})
    return {"available": not any(c["status"] == "failed" for c in checks),
            "checks": checks, "task_count": len(receipt["tasks"])}


def job_environment(host: HostConfig, receipt: dict[str, Any]) -> dict[str, Any]:
    return environment_config(host, receipt["runtime"])
