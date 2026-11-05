"""Harbor-backed benchmark adapter preserving the complete FruitFlyAgent harness."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Mapping


from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.workspace import WorkspacePaths
from fruitfly_eval.contracts import EvaluationRequest, RESULT_SCHEMA_VERSION
from dataclasses import asdict

from .base import BenchmarkDescriptor, BenchmarkVariant, PreflightResult, ProgressSink
from fruitfly_eval.runner import run_harbor_job
from fruitfly_eval.runtime import prepare_runtime
from fruitfly_eval.results import load_harbor_job_result, parse_harbor_job_result
from fruitfly_eval.harbor.host import HostConfig
from fruitfly_eval.harbor.preparation import inspect as inspect_preparation, job_environment, load_preparation
from fruitfly_eval.harbor.dependencies import dependency_environment
from fruitfly_eval.harbor.material import write_json
from fruitfly_eval.harbor.tasks import validate_coverage, coverage_report
from fruitfly_eval.harbor.budget import execution_budget


HARBOR_AGENT_IMPORT = "fruitfly_eval.harbor_agent:FruitFlyHarborAgent"


def harbor_descriptor(*, benchmark_id: str, label: str, description: str,
                      version: str, dataset: str, smoke_task: str) -> BenchmarkDescriptor:
    """Declare a dataset using the shared container execution and reward contract."""
    return BenchmarkDescriptor(
        benchmark_id=benchmark_id, label=label, description=description,
        version=version, dataset=dataset, adapter_version="8",
        variants=(
            BenchmarkVariant("smoke", "Single-task smoke", "Validate one complete evaluation path",
                             task_names=(smoke_task,)),
            BenchmarkVariant("no_gpu", "Tasks without GPU requirements", "Exclude tasks declaring GPUs in any effective environment or Compose service"),
            BenchmarkVariant("full", "Full dataset", "Run every resolved task with its declared resources"),
        ),
        metric_names=("success_rate", "official_reward", "error_rate", "timeout_rate",
                      "input_tokens", "output_tokens", "cost_usd", "latency_ms"),
        network={"provider": True, "control_plane": True, "task_environment": True, "verifier": True},
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
    ) -> None:
        self._harbor_command = harbor_command
        self._docker_command = docker_command
        self.host_config_path: str | None = None

    def configure_host(self, path: str) -> None:
        self.host_config_path = path

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
                            "Docker engine is unavailable; check the selected Docker context, "
                            "daemon and socket access with `docker info`"
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
        preflight = self.preflight(variant)
        if not preflight.available:
            raise RuntimeError(str(next(item for item in preflight.checks if not item["ok"])["detail"]))
        host = HostConfig.read(Path(request.runtime.working_directory), self.host_config_path)
        preparation = load_preparation(host, self.descriptor, variant)
        readiness = inspect_preparation(request, self.descriptor, host, docker=self._docker_command or "docker", receipt=preparation)
        if not readiness["available"]:
            raise ValueError("Harbor preparation check failed: " + json.dumps(readiness["checks"]))
        from fruitfly_eval.task_selection import select_prepared_tasks
        preparation = select_prepared_tasks(preparation, request.benchmark.task_names)
        runtime, execution = asdict(request.runtime), asdict(request.execution)
        job_root = result_path.parent / "harbor"
        job_root.mkdir(parents=True, exist_ok=True)
        write_json(job_root / "preparation.json", preparation)
        write_json(job_root / "readiness.json", readiness)
        paths = WorkspacePaths(Path(request.runtime.working_directory))
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
            config_path=config_path, model_catalog=model_catalog,
            profile=selected_profile, secret_names=secret_names, host=host, preparation=preparation)
        budget = execution_budget(preparation['tasks'], request.execution.attempts,
            request.execution.concurrency, request.execution.timeout_seconds)
        budget['evidence_capture'] = {
            'max_bytes_per_pass': host.evidence['max_total_bytes'],
            'max_final_bytes_all_attempts': host.evidence['max_total_bytes'] * len(preparation['tasks']) * request.execution.attempts,
            'max_entries_per_pass': host.evidence['max_entries'],
            'baseline_seconds': host.evidence['baseline_seconds'],
            'capture_seconds': host.evidence['capture_seconds'],
            'note': 'Additional per-phase job wall time; transfer/index storage and multi-step phases are additional. Bounds are not runtime predictions.'}
        write_json(job_root / 'execution-budget.json', budget)
        if progress is not None:
            progress({'type': 'execution_budget', **budget})
        if progress is not None:
            progress({"type": "job_started", "job_id": job_name, "artifacts_path": str(job_root)})
        runner_error = None
        try:
            code, detail = run_harbor_job(command, environment=environment,
                timeout=request.execution.timeout_seconds, job_root=job_root, progress=progress, job_id=job_name,
                docker=self._docker_command or "docker")
            if code:
                runner_error = f"Harbor exited with {code}: {detail[-2000:]}"
        except (RuntimeError, KeyboardInterrupt) as exc:
            runner_error = str(exc) or "evaluation interrupted"
        job_result_path = job_root / job_name / "result.json"
        errors = {"runner": runner_error} if runner_error else {}
        if not job_result_path.parent.is_dir():
            candidates = tuple(job_root.glob("*/result.json"))
            if len(candidates) == 1:
                job_result_path = candidates[0]
            else:
                errors['results'] = 'Harbor did not create a unique job result; inspect harbor.log'
        trials: list[dict[str, Any]] = []
        metrics: list[dict[str, Any]] = []
        if 'results' not in errors:
            try:
                data = load_harbor_job_result(job_result_path, allow_partial=True)
                trials, metrics = parse_harbor_job_result(data, job_id=job_name)
            except (OSError, ValueError) as exc:
                errors['results'] = str(exc)
        try:
            validate_coverage(preparation["tasks"], trials, request.execution.attempts)
        except ValueError as exc:
            errors["coverage"] = str(exc)
            metrics = []  # Partial samples cannot establish a full selection score.
        coverage = coverage_report(preparation['tasks'], trials, request.execution.attempts)
        resume_requests = []
        for missing in sorted(set(coverage['missing_results'].values())):
            names = [task['name'] for task in preparation['tasks'] if coverage['missing_results'].get(task['id']) == missing]
            draft = request.to_dict()
            draft['benchmark']['task_names'] = names
            draft['execution']['attempts'] = missing
            resume_requests.append({'request': draft, 'requires_configuration_review': True})
        write_json(job_root / 'resume-requests.json', {'requests': resume_requests,
            'note': 'Review runtime source/model identities before executing. Drafts do not resume or combine scores automatically.'})
        payload: dict[str, Any] = {"schema_version": RESULT_SCHEMA_VERSION, "status": "failed" if errors else "completed", "metrics": metrics,
            "errors": errors, "trials": trials, "coverage": coverage, "budget": budget,
            "artifacts": [{"kind": "execution_budget", "path": str(job_root / "execution-budget.json")},
                          {"kind": "resume_requests", "path": str(job_root / "resume-requests.json")},
                          {"kind": "harbor_job", "path": str(job_result_path.parent)},
                          {"kind": "harbor_log", "path": str(job_root / "harbor.log")},
                          {"kind": "runtime_config", "path": str(config_path)},
                          {"kind": "model_catalog", "path": str(model_catalog)},
                          {"kind": "preparation", "path": str(job_root / "preparation.json")},
                          {"kind": "readiness", "path": str(job_root / "readiness.json")}]}
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
        config_path: Path,
        model_catalog: Path,
        profile: str,
        secret_names: tuple[str, ...],
        host: HostConfig,
        preparation: dict[str, Any],
    ) -> list[str]:
        selected = next((item for item in self.descriptor.variants if item.variant_id == variant), None)
        if selected is None:
            raise ValueError(f"unknown execution profile {variant!r}")
        if not preparation["tasks"]:
            raise ValueError("prepared task selection is empty")
        payload = {
            "job_name": job_name, "jobs_dir": str(jobs_dir),
            "n_attempts": int(execution.get("attempts", 1)),
            "n_concurrent_trials": int(execution.get("concurrency", 1)),
            "retry": {"max_retries": 0},
            "environment": job_environment(host, preparation),
            "verifier": {"env": {**dependency_environment(host), **host.verifier_env}},
            "tasks": [{"path": task["path"], "source": dataset} for task in preparation["tasks"]],
            "agents": [{"import_path": HARBOR_AGENT_IMPORT, "kwargs": {
                "config_path": str(config_path),
                "model_catalog_path": str(model_catalog), "profile": profile,
                "secret_names": ",".join(secret_names),
            }}],
        }
        config = jobs_dir / "harbor-job.json"
        write_json(config, payload)
        return [executable, "run", "--config", str(config), "--yes",
                "--plugin", "fruitfly_eval.harbor.evidence_hooks:EvidenceCapturePlugin"]


__all__ = ["HARBOR_AGENT_IMPORT", "HarborBenchmarkAdapter", "harbor_descriptor"]
