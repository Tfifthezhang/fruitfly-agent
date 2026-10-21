"""Harbor-backed benchmark adapter preserving the complete FruitFlyAgent harness."""

from __future__ import annotations

import json
from collections import Counter
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Mapping


from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.workspace import WorkspacePaths
from eval.installation import resolve_installation
from eval.contracts import EvaluationRequest, SCHEMA_VERSION
from dataclasses import asdict

from .base import BenchmarkDescriptor, BenchmarkVariant, PreflightResult, ProgressSink
from eval.runner import run_harbor_job
from eval.runtime import prepare_runtime
from eval.results import load_harbor_job_result, parse_harbor_job_result


HARBOR_AGENT_IMPORT = "eval.harbor_agent:FruitFlyHarborAgent"


def harbor_descriptor(*, benchmark_id: str, label: str, description: str,
                      version: str, dataset: str, smoke_task: str,
                      subsets: tuple[BenchmarkVariant, ...] = ()) -> BenchmarkDescriptor:
    """Declare a dataset using the shared container execution and reward contract."""
    return BenchmarkDescriptor(
        benchmark_id=benchmark_id, label=label, description=description,
        version=version, dataset=dataset, adapter_version="5",
        variants=(
            BenchmarkVariant("smoke", "Single-task smoke", "Validate one complete evaluation path",
                             task_names=(smoke_task,)),
            *subsets,
            BenchmarkVariant("no_gpu", "Full dataset · CPU host", "Run the full dataset without a GPU preflight"),
            BenchmarkVariant("gpu", "Full dataset · GPU host", "Run the full dataset with a GPU preflight",
                             requires_gpu=True),
        ),
        metric_names=("success_rate", "official_reward", "error_rate", "timeout_rate",
                      "input_tokens", "output_tokens", "cost_usd", "latency_ms"),
        network={"provider": True, "control_plane": True, "task_environment": True, "verifier": False},
        isolation="harbor_task_container", smoke_task=smoke_task,
    )


def _harbor_executable() -> str | None:
    """Find Harbor in the active Python environment before searching PATH."""
    alongside_python = Path(sys.executable).with_name("harbor")
    if alongside_python.is_file() and os.access(alongside_python, os.X_OK):
        return str(alongside_python)
    return shutil.which("harbor")


def _docker_check(command: str, *arguments: str, failure: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            (command, *arguments),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "detail": failure}
    return {
        "ok": completed.returncode == 0,
        "detail": (
            completed.stdout.strip() if completed.returncode == 0 else failure
        ),
    }


class HarborBenchmarkAdapter:
    """Run official benchmark tasks with FruitFlyAgent as a Harbor installed agent."""

    descriptor: BenchmarkDescriptor

    def __init__(
        self,
        *,
        harbor_command: str | None = None,
        docker_command: str | None = None,
        gpu_command: str | None = None,
    ) -> None:
        self._harbor_command = harbor_command
        self._docker_command = docker_command
        self._gpu_command = gpu_command

    def preflight(self, variant: str) -> PreflightResult:
        variants = {item.variant_id for item in self.descriptor.variants}
        if variant not in variants:
            return PreflightResult(
                False,
                (
                    {
                        "id": "variant",
                        "ok": False,
                        "detail": f"unknown execution profile {variant!r}",
                    },
                ),
            )
        harbor = self._harbor_command or _harbor_executable()
        docker = self._docker_command or shutil.which("docker")
        checks: list[Mapping[str, Any]] = [
            {
                "id": "harbor",
                "ok": bool(harbor),
                "detail": (
                    str(harbor)
                    if harbor
                    else "install the benchmark extra: pip install -e '.[benchmarks]'"
                ),
            },
            {
                "id": "docker",
                "ok": bool(docker),
                "detail": str(docker) if docker else "Docker CLI was not found",
            },
        ]
        if docker:
            checks.append(
                {
                    "id": "docker_daemon",
                    **_docker_check(
                        str(docker),
                        "info",
                        "--format",
                        "{{.ServerVersion}}",
                        failure=(
                            "Docker engine is unavailable; start Docker Desktop or "
                            "Colima, then run `docker info`"
                        ),
                    ),
                }
            )
            checks.append(
                {
                    "id": "docker_compose",
                    **_docker_check(
                        str(docker),
                        "compose",
                        "version",
                        "--short",
                        failure=(
                            "Docker Compose v2 is unavailable; install its plugin "
                            "and run `docker compose version`"
                        ),
                    ),
                }
            )
        if next(item for item in self.descriptor.variants if item.variant_id == variant).requires_gpu:
            gpu = self._gpu_command or shutil.which("nvidia-smi")
            checks.append(
                {
                    "id": "gpu",
                    "ok": bool(gpu),
                    "detail": (
                        str(gpu) if gpu else "NVIDIA GPU runtime was not detected"
                    ),
                }
            )
        return PreflightResult(
            all(bool(item["ok"]) for item in checks),
            tuple(checks),
            (str(harbor),) if harbor else (),
        )

    def run(
        self, *, request_path: Path, result_path: Path, variant: str,
        progress: ProgressSink | None = None,
    ) -> None:
        request = EvaluationRequest.read(request_path)
        if request.benchmark.benchmark_id != self.descriptor.benchmark_id or request.benchmark.variant != variant:
            raise ValueError("runner benchmark selection differs from request")
        source_root = resolve_installation(os.environ.get("FRUITFLY_EVAL_PACKAGE"),
                                           checkout=Path(__file__).resolve().parents[2])
        preflight = self.preflight(variant)
        if not preflight.available:
            raise RuntimeError(str(next(item for item in preflight.checks if not item["ok"])["detail"]))
        runtime, execution = asdict(request.runtime), asdict(request.execution)
        job_root = result_path.parent / "harbor"
        job_root.mkdir(parents=True, exist_ok=True)
        paths = WorkspacePaths(Path(request.runtime.working_directory))
        for notice in paths.notices():
            print(f"notice: {notice}", file=sys.stderr)
        environment = {**load_env(paths.secret_file()), **os.environ}
        config_path, model_catalog, secret_names = prepare_runtime(runtime=runtime, output_dir=job_root, environment=environment)
        selected_profile = request.runtime.profile
        receipt = job_root / "runtime.json"
        if receipt.is_file():
            selected_profile = json.loads(receipt.read_text(encoding="utf-8"))["profile"]
        if not selected_profile:
            raise ValueError("prepared runtime has no selected profile")
        job_name = self.descriptor.benchmark_id
        command = self._command(executable=preflight.command[0], dataset=self.descriptor.dataset,
            variant=variant, execution=execution, jobs_dir=job_root, job_name=job_name,
            source_root=source_root, config_path=config_path, model_catalog=model_catalog,
            profile=selected_profile, secret_names=secret_names)
        if progress is not None:
            progress({"type": "job_started", "job_id": job_name, "artifacts_path": str(job_root)})
        code, detail = run_harbor_job(command, environment=environment,
            timeout=request.execution.timeout_seconds, job_root=job_root, progress=progress, job_id=job_name)
        if code:
            raise RuntimeError(f"Harbor exited with {code}: {detail[-2000:]}\nFull runner log: {job_root / 'harbor.log'}")
        job_result_path = job_root / job_name / "result.json"
        if not job_result_path.is_file():
            candidates = tuple(job_root.glob("*/result.json"))
            if len(candidates) != 1:
                raise RuntimeError("Harbor did not create a unique job result")
            job_result_path = candidates[0]
        trials, metrics = parse_harbor_job_result(load_harbor_job_result(job_result_path), job_id=job_name)
        selected_names = next(item.task_names for item in self.descriptor.variants if item.variant_id == variant)
        if selected_names:
            expected = Counter({name: request.execution.attempts for name in selected_names})
            if Counter(trial["task_id"] for trial in trials) != expected:
                raise ValueError("Harbor results do not match the selected task batch and attempt count")
        payload: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "status": "completed", "metrics": metrics,
            "errors": {}, "trials": trials,
            "artifacts": [{"kind": "harbor_job", "path": str(job_result_path.parent)},
                          {"kind": "harbor_log", "path": str(job_root / "harbor.log")},
                          {"kind": "runtime_config", "path": str(config_path)},
                          {"kind": "model_catalog", "path": str(model_catalog)}]}
        if receipt.is_file():
            payload["artifacts"].append({"kind": "runtime_snapshot", "path": str(receipt)})
            payload["runtime_snapshot"] = json.loads(receipt.read_text(encoding="utf-8"))
        result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if progress is not None:
            progress({"type": "job_finished", "job_id": job_name, "completed": len(trials)})

    def _command(
        self,
        *,
        executable: str,
        dataset: str,
        variant: str,
        execution: Mapping[str, Any],
        jobs_dir: Path,
        job_name: str,
        source_root: Path,
        config_path: Path,
        model_catalog: Path,
        profile: str,
        secret_names: tuple[str, ...],
    ) -> list[str]:
        command = [
            executable,
            "run",
            "--dataset",
            dataset,
            "--agent",
            HARBOR_AGENT_IMPORT,
            "--env",
            "docker",
            "--n-attempts",
            str(execution.get("attempts", 1)),
            "--n-concurrent",
            str(execution.get("concurrency", 1)),
            "--jobs-dir",
            str(jobs_dir),
            "--job-name",
            job_name,
            "--yes",
            "--agent-kwarg",
            f"source_root={source_root}",
            "--agent-kwarg",
            f"config_path={config_path}",
            "--agent-kwarg",
            f"model_catalog_path={model_catalog}",
            "--agent-kwarg",
            f"profile={profile}",
            "--agent-kwarg",
            f"secret_names={','.join(secret_names)}",
        ]
        selected = next((item for item in self.descriptor.variants if item.variant_id == variant), None)
        if selected is None:
            raise ValueError(f"unknown execution profile {variant!r}")
        task_names = selected.task_names
        if variant == "smoke" and not task_names:
            if not self.descriptor.smoke_task:
                raise ValueError(
                    f"{self.descriptor.benchmark_id} does not declare a smoke task"
                )
            task_names = (self.descriptor.smoke_task,)
        if task_names:
            for name in task_names:
                command.extend(("--include-task-name", name))
            command.extend(("--n-tasks", str(len(task_names))))
        return command


__all__ = ["HARBOR_AGENT_IMPORT", "HarborBenchmarkAdapter", "harbor_descriptor"]
