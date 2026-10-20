"""Execute one immutable original task with a host-owned runtime trial packet."""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path

from eval.catalog import builtin_catalog
from eval.contracts import RuntimeReference
from eval.evidence import export_harbor_evidence, material_hash
from eval.installation import validate_installation
from eval.benchmarks.harbor import HarborBenchmarkAdapter, _runtime_files, _run_harbor_job
from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.workspace import WorkspacePaths
from fruitfly_agent.lab.improvement.api import TaskReference
from fruitfly_agent.lab.improvement.contracts.versions import canonical_json


def run_trial(request: dict, *, output_root: Path, progress=None):
    required = {"schema_version", "runtime", "benchmark_id", "task", "task_path", "source_root", "packet", "timeout_seconds"}
    if not isinstance(request, dict) or set(request) != required or request["schema_version"] != 1:
        raise ValueError("invalid external trial request")
    task = TaskReference.from_dict(request["task"])
    runtime = RuntimeReference.from_dict(request["runtime"])
    if type(request["timeout_seconds"]) is not int or request["timeout_seconds"] < 1:
        raise ValueError("external trial deadline must be a positive integer")
    task_path = Path(request["task_path"]).resolve()
    if material_hash(task_path) != task.material_hash:
        raise ValueError("original task material changed before trial")
    source = validate_installation(Path(request["source_root"]))
    if not source.is_dir():
        raise ValueError("versioned runtime trials require a source snapshot")
    adapter = builtin_catalog().get(request["benchmark_id"])
    if not isinstance(adapter, HarborBenchmarkAdapter):
        raise ValueError("the selected benchmark has no isolated task executor")
    if adapter.descriptor.dataset != task.dataset:
        raise ValueError("task dataset differs from selected benchmark")
    preflight = adapter.preflight("no_gpu")
    if not preflight.available:
        raise RuntimeError("external trial preflight failed")
    output_root.mkdir(parents=True, exist_ok=False)
    packet_path = output_root / "trial-request.json"
    packet_path.write_text(canonical_json(request["packet"]), encoding="utf-8")
    config, models, secret_names = _runtime_files(runtime=asdict(runtime), output_dir=output_root)
    environment = {**load_env(WorkspacePaths(Path(runtime.working_directory)).secret_file()), **os.environ}
    command = adapter._command(executable=preflight.command[0], dataset=task.dataset, variant="no_gpu",
        execution={"attempts": 1, "concurrency": 1}, jobs_dir=output_root, job_name="trial",
        source_root=source, config_path=config, model_catalog=models, profile=runtime.profile, secret_names=secret_names)
    at = command.index("--dataset")
    command[at:at + 2] = ["--path", str(task_path)]
    command.extend(("--n-tasks", "1", "--agent-kwarg", "trial_request_path=" + str(packet_path)))
    code, detail = _run_harbor_job(command, environment=environment, timeout=request["timeout_seconds"],
                                  job_root=output_root, progress=progress, job_id="trial")
    if code:
        raise RuntimeError("external task runner failed; inspect owned trial logs")
    evidence_root = output_root / "evidence"
    exported = export_harbor_evidence(output_root / "trial", dataset=task.dataset,
        output_directory=evidence_root, material_resolver=lambda raw: task_path)
    if exported["errors"] or len(exported["runs"]) != 1:
        raise ValueError("external trial did not produce one complete task receipt")
    row = exported["runs"][0]
    # A local snapshot path can change Harbor's display name. The host binds its
    # authoritative reference only after verifying the exact owned task bytes.
    if row["task"]["material_hash"] != task.material_hash or material_hash(task_path) != task.material_hash:
        raise ValueError("trial did not retain its original task material")
    row["task"] = task.to_dict()
    return {"schema_version": 1, "evidence": row, "evidence_root": str(evidence_root)}
