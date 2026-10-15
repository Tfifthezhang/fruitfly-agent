"""Harbor-backed benchmark adapter preserving the complete FruitFlyAgent harness."""

from __future__ import annotations

import json
from collections import Counter
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping

import yaml

from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.workspace import WorkspacePaths
from eval.installation import resolve_installation
from eval.contracts import EvaluationRequest, SCHEMA_VERSION
from dataclasses import asdict

from .base import BenchmarkDescriptor, PreflightResult, ProgressSink


HARBOR_AGENT_IMPORT = "eval.harbor_agent:FruitFlyHarborAgent"


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
        if variant == "gpu":
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
        config_path, model_catalog, secret_names = _runtime_files(runtime=runtime, output_dir=job_root)
        job_name = self.descriptor.benchmark_id
        command = self._command(executable=preflight.command[0], dataset=self.descriptor.dataset,
            variant=variant, execution=execution, jobs_dir=job_root, job_name=job_name,
            source_root=source_root, config_path=config_path, model_catalog=model_catalog,
            profile=request.runtime.profile, secret_names=secret_names)
        if progress is not None:
            progress({"type": "job_started", "job_id": job_name, "artifacts_path": str(job_root)})
        code, detail = _run_harbor_job(command, environment=environment,
            timeout=request.execution.timeout_seconds, job_root=job_root, progress=progress, job_id=job_name)
        if code:
            raise RuntimeError(f"Harbor exited with {code}: {detail[-2000:]}\nFull runner log: {job_root / 'harbor.log'}")
        job_result_path = job_root / job_name / "result.json"
        if not job_result_path.is_file():
            candidates = tuple(job_root.glob("*/result.json"))
            if len(candidates) != 1:
                raise RuntimeError("Harbor did not create a unique job result")
            job_result_path = candidates[0]
        trials, metrics = parse_harbor_job_result(_load_harbor_job_result(job_result_path), job_id=job_name)
        selected_names = next(item.task_names for item in self.descriptor.variants if item.variant_id == variant)
        if selected_names:
            expected = Counter({name: request.execution.attempts for name in selected_names})
            if Counter(trial["task_id"] for trial in trials) != expected:
                raise ValueError("Harbor results do not match the selected task batch and attempt count")
        from eval.evidence import export_harbor_evidence
        evidence_root = job_root / "evidence"
        export_harbor_evidence(job_result_path.parent, dataset=self.descriptor.dataset,
                               output_directory=evidence_root)
        payload = {"schema_version": SCHEMA_VERSION, "status": "completed", "metrics": metrics,
            "errors": {}, "trials": trials,
            "artifacts": [{"kind": "harbor_job", "path": str(job_result_path.parent)},
                          {"kind": "benchmark_evidence", "path": str(evidence_root / "evidence.json")},
                          {"kind": "harbor_log", "path": str(job_root / "harbor.log")},
                          {"kind": "runtime_config", "path": str(config_path)},
                          {"kind": "model_catalog", "path": str(model_catalog)}]}
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


def _run_harbor_job(
    command: list[str], *, environment: Mapping[str, str], timeout: int,
    job_root: Path, progress: ProgressSink | None, job_id: str,
) -> tuple[int, str]:
    """Retry transient registry errors only before Harbor creates a job."""

    deadline = time.monotonic() + timeout
    log_offsets: dict[Path, int] = {}
    for attempt in range(1, 4):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(f"Harbor job timed out after {timeout} seconds")
        code, detail = _run_harbor_job_once(
            command, environment=environment, timeout=remaining,
            job_root=job_root, progress=progress,
            job_id=job_id, log_offsets=log_offsets,
        )
        path = job_root / "harbor.log"
        text = path.read_text(encoding="utf-8", errors="replace")
        transient_registry_failure = (
            code != 0 and "Error getting dataset " in text
            and any(error in text for error in ("ConnectError", "ConnectTimeout", "ReadTimeout"))
            # Harbor creates its job directory after dataset resolution. Once
            # any directory exists, model/task side effects cannot be ruled out.
            and not any(item.is_dir() for item in job_root.iterdir())
        )
        if not transient_registry_failure or attempt == 3 or deadline - time.monotonic() <= 1:
            return code, detail
        archive = job_root / f"harbor-attempt-{attempt}.log"
        path.replace(archive)
        log_offsets[archive] = archive.stat().st_size
        log_offsets.pop(path, None)
        if progress is not None:
            progress({
                "type": "log", "job_id": job_id, "source": "registry",
                "text": f"Registry connection failed before job creation; retry {attempt + 1}/3. Previous output: {archive.name}\n",
            })
        time.sleep(1)
    raise AssertionError("unreachable")


def _run_harbor_job_once(
    command: list[str], *, environment: Mapping[str, str], timeout: float,
    job_root: Path, progress: ProgressSink | None, job_id: str,
    log_offsets: dict[Path, int],
) -> tuple[int, str]:
    """Stream ephemeral display events; the normal session remains the record."""

    offsets: dict[Path, int] = {}
    fragments: dict[Path, bytes] = {}
    finished_trials: set[Path] = set()
    started_agents: set[str] = set()
    finished_agents: set[str] = set()

    def observe(event: dict[str, Any]) -> None:
        if event.get("type") == "agent_event":
            payload = event.get("event", {})
            trial_id = str(event.get("trial_id", ""))
            if payload.get("type") == "run_started":
                started_agents.add(trial_id)
            elif payload.get("type") == "run_finished":
                finished_agents.add(trial_id)
        if progress is not None:
            progress(event)

    log_fragments: dict[Path, bytes] = {}
    output_path = job_root / "harbor.log"
    with output_path.open("w+b") as output:
        process = subprocess.Popen(
            command, stdout=output, stderr=subprocess.STDOUT,
            env=dict(environment),
        )
        started_at = time.monotonic()
        deadline = started_at + timeout
        next_update = started_at
        try:
            while process.poll() is None:
                if progress is not None:
                    _forward_agent_events(
                        job_root, job_id, offsets, fragments, observe
                    )
                    _forward_trial_results(
                        job_root, job_id, finished_trials, observe
                    )
                    _forward_logs(job_root, job_id, log_offsets, log_fragments, progress)
                    now = time.monotonic()
                    if now >= next_update:
                        progress({
                            "type": "job_progress", "job_id": job_id,
                            "elapsed_seconds": int(now - started_at),
                            "completed": len(finished_trials),
                            "agent_runs_started": len(started_agents),
                            "active_agents": len(started_agents - finished_agents),
                        })
                        next_update = now + 5
                if time.monotonic() >= deadline:
                    process.kill()
                    process.wait()
                    raise RuntimeError(f"Harbor job timed out after {timeout} seconds")
                time.sleep(0.2)
            if progress is not None:
                _forward_agent_events(
                    job_root, job_id, offsets, fragments, observe
                )
                _forward_trial_results(
                    job_root, job_id, finished_trials, observe
                )
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if progress is not None:
                _forward_logs(
                    job_root, job_id, log_offsets, log_fragments,
                    progress, final=True,
                )
            # Archive the complete event stream for post-run inspection.
            for path in job_root.glob("*/*/agent/live-events.jsonl"):
                path.replace(path.with_name("events.jsonl"))
        output.seek(0, os.SEEK_END)
        output.seek(max(0, output.tell() - 4000))
        return process.returncode, output.read().decode("utf-8", errors="replace").strip()


def _forward_logs(
    job_root: Path, job_id: str,
    offsets: dict[Path, int], fragments: dict[Path, bytes],
    progress: ProgressSink, *, final: bool = False,
) -> None:
    """Tail durable runner/setup/verifier logs, including partial final lines."""

    paths = {job_root / "harbor.log"}
    paths.update(job_root.rglob("*.log"))
    paths.update(job_root.rglob("exception.txt"))
    paths.update(job_root.glob("*/*/verifier/*.txt"))
    for path in sorted(paths):
        previous = offsets.get(path, 0)
        try:
            with path.open("rb") as handle:
                if path.stat().st_size < previous:
                    previous = 0
                    fragments.pop(path, None)
                handle.seek(previous)
                chunk = handle.read()
        except OSError:
            continue
        offsets[path] = previous + len(chunk)
        data = fragments.get(path, b"") + chunk
        if final:
            lines, fragments[path] = data, b""
        else:
            boundary = data.rfind(b"\n") + 1
            lines, fragments[path] = data[:boundary], data[boundary:]
        text = lines.decode("utf-8", errors="replace")
        # Keep each JSONL envelope below the subprocess reader's line limit.
        for start in range(0, len(text), 4096):
            progress({
                "type": "log", "job_id": job_id,
                "source": str(path.relative_to(job_root)),
                "text": text[start:start + 4096],
            })


def _forward_agent_events(
    job_root: Path, job_id: str,
    offsets: dict[Path, int], fragments: dict[Path, bytes],
    progress: ProgressSink,
) -> None:
    for path in job_root.glob("*/*/agent/live-events.jsonl"):
        previous = offsets.get(path, 0)
        try:
            with path.open("rb") as handle:
                handle.seek(previous)
                chunk = handle.read()
        except OSError:
            continue
        if not chunk:
            continue
        offsets[path] = previous + len(chunk)
        data = fragments.get(path, b"") + chunk
        *lines, remainder = data.split(b"\n")
        fragments[path] = remainder
        for line in lines:
            try:
                event = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(event, dict) and isinstance(event.get("type"), str):
                progress({
                    "type": "agent_event", "job_id": job_id,
                    "trial_id": path.parent.parent.name, "event": event,
                })


def _forward_trial_results(
    job_root: Path, job_id: str,
    seen: set[Path], progress: ProgressSink,
) -> None:
    for path in job_root.glob("*/*/result.json"):
        if path in seen:
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        seen.add(path)
        progress({
            "type": "trial_finished", "job_id": job_id,
            "trial_id": path.parent.name, "completed": len(seen),
            "error": value.get("exception_info"),
        })


def _runtime_files(
    *,
    runtime: Mapping[str, Any],
    output_dir: Path,
) -> tuple[Path, Path, tuple[str, ...]]:
    original_config = Path(str(runtime.get("config_path", ""))).resolve()
    profile_id = str(runtime.get("profile", ""))
    raw_config = yaml.safe_load(original_config.read_text(encoding="utf-8"))
    if not isinstance(raw_config, Mapping):
        raise ValueError("harness config must be a mapping")
    profiles = raw_config.get("profiles")
    if not isinstance(profiles, Mapping) or not isinstance(profiles.get(profile_id), Mapping):
        raise ValueError(f"harness profile {profile_id!r} is missing")
    profile = dict(profiles[profile_id])
    model = profile.get("model")
    mechanisms = profile.get("mechanisms")
    if not isinstance(model, Mapping) or not isinstance(mechanisms, list):
        raise ValueError(f"harness profile {profile_id!r} has invalid model or mechanisms")
    source_catalog = Path(str(model.get("catalog", "models.yaml")))
    if not source_catalog.is_absolute():
        source_catalog = original_config.parent / source_catalog
    source_catalog = source_catalog.resolve()
    if not source_catalog.is_file():
        raise FileNotFoundError(f"model catalog not found: {source_catalog}")
    remote_catalog = "/installed-agent/fruitfly/runtime/models.yaml"
    adjusted_profile = dict(profile)
    adjusted_model = dict(model)
    adjusted_model["catalog"] = remote_catalog
    adjusted_profile["model"] = adjusted_model
    adjusted_profile["mechanisms"] = mechanisms
    adjusted = {
        "schema_version": raw_config.get("schema_version", 1),
        "default_profile": profile_id,
        "profiles": {profile_id: adjusted_profile},
    }
    config_path = output_dir / "config.yaml"
    model_path = output_dir / "models.yaml"
    config_path.write_text(
        yaml.safe_dump(adjusted, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    shutil.copyfile(source_catalog, model_path)
    return config_path, model_path, _secret_names(model_path)


def _secret_names(model_catalog: Path) -> tuple[str, ...]:
    data = yaml.safe_load(model_catalog.read_text(encoding="utf-8"))
    found: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                if key == "api_key_env" and isinstance(nested, str) and nested:
                    found.add(nested)
                else:
                    visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(data)
    return tuple(sorted(found))


def _load_harbor_job_result(path: Path) -> Mapping[str, Any]:
    """Load Harbor's job summary and its separately stored trial results."""
    result = dict(_load_object(path))
    embedded = result.get("trial_results")
    if embedded:
        return result
    trial_paths = sorted(path.parent.glob("*/result.json"))
    expected = result.get("n_total_trials")
    if (
        isinstance(expected, int)
        and not isinstance(expected, bool)
        and expected > len(trial_paths)
    ):
        raise ValueError(
            f"Harbor job has {len(trial_paths)} of {expected} trial result files"
        )
    result["trial_results"] = [_load_object(trial_path) for trial_path in trial_paths]
    return result


def parse_harbor_job_result(
    data: Mapping[str, Any],
    *,
    job_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_trials = data.get("trial_results", [])
    if not isinstance(raw_trials, list):
        raise ValueError("Harbor result trial_results must be a list")
    if not raw_trials:
        raise ValueError("Harbor result contains no trials")
    trials: list[dict[str, Any]] = []
    rewards: list[float] = []
    errors = 0
    timeouts = 0
    input_tokens = 0
    output_tokens = 0
    costs = 0.0
    usage_samples = 0
    cost_samples = 0
    latencies: list[float] = []
    for index, raw in enumerate(raw_trials):
        trial = _mapping(raw, "Harbor trial")
        exception = trial.get("exception_info")
        reward = _official_reward(trial)
        agent_result = trial.get("agent_result")
        status, error, timed_out = _trial_status(exception, reward)
        errors += int(error is not None)
        timeouts += int(timed_out)
        if error is None and reward is not None:
            rewards.append(reward)
        if isinstance(agent_result, Mapping):
            raw_input = agent_result.get("n_input_tokens")
            raw_output = agent_result.get("n_output_tokens")
            if _is_integer(raw_input) or _is_integer(raw_output):
                usage_samples += 1
                input_tokens += _integer(raw_input)
                output_tokens += _integer(raw_output)
            raw_cost = agent_result.get("cost_usd")
            if isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool):
                cost_samples += 1
                costs += _number(raw_cost)
        latency_ms = _duration_ms(trial.get("agent_execution"))
        if latency_ms is not None:
            latencies.append(latency_ms)
        task_id = str(trial.get("task_name") or trial.get("trial_name") or index)
        metrics = (
            []
            if reward is None or error is not None
            else [{"name": "official_reward", "value": reward}]
        )
        trials.append(
            {
                "trial_id": str(trial.get("id") or f"{job_id}-{index}"),
                "task_id": task_id,
                "status": status,
                "metrics": metrics,
                "error": error,
                "runtime": _runtime_metadata(agent_result),
            }
        )
    count = len(raw_trials)
    success_count = sum(item["status"] == "passed" for item in trials)
    values = {
        "success_rate": success_count / count if count else None,
        "official_reward": sum(rewards) / len(rewards) if rewards else None,
        "error_rate": errors / count if count else None,
        "timeout_rate": timeouts / count if count else None,
        "input_tokens": input_tokens if usage_samples else None,
        "output_tokens": output_tokens if usage_samples else None,
        "cost_usd": costs if cost_samples else None,
        "latency_ms": sum(latencies) / len(latencies) if latencies else None,
    }
    return trials, _benchmark_metrics(values, count)


def _official_reward(trial: Mapping[str, Any]) -> float | None:
    verifier = trial.get("verifier_result")
    raw_rewards = verifier.get("rewards") if isinstance(verifier, Mapping) else None
    reward_map = raw_rewards if isinstance(raw_rewards, Mapping) else {}
    numeric_rewards = [
        float(value) for value in reward_map.values()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return (
        float(reward_map["reward"])
        if isinstance(reward_map.get("reward"), (int, float))
        else (numeric_rewards[0] if len(numeric_rewards) == 1 else None)
    )


def _runtime_metadata(agent_result: object) -> dict | None:
    metadata = agent_result.get("metadata") if isinstance(agent_result, Mapping) else None
    manifest = metadata.get("runtime_manifest") if isinstance(metadata, Mapping) else None
    return dict(manifest) if isinstance(manifest, Mapping) else None


def _trial_status(exception: object, reward: float | None) -> tuple[str, dict[str, str] | None, bool]:
    if isinstance(exception, Mapping):
        kind = str(exception.get("exception_type", ""))
        return "error", {"type": kind or "HarborTrialError", "message": str(exception.get("exception_message", ""))}, "timeout" in kind.lower()
    return ("passed" if reward is not None and reward >= 1.0 else "failed"), None, False


def _benchmark_metrics(
    values: Mapping[str, int | float | None], count: int,
) -> list[dict[str, Any]]:
    units = {
        "success_rate": "ratio",
        "official_reward": "score",
        "error_rate": "ratio",
        "timeout_rate": "ratio",
        "input_tokens": "tokens",
        "output_tokens": "tokens",
        "cost_usd": "USD",
        "latency_ms": "ms",
    }
    lower = {"error_rate", "timeout_rate", "cost_usd", "latency_ms"}
    metrics = [
        {
            "name": name,
            "value": value,
            "unit": units[name],
            "direction": "lower_is_better" if name in lower else "higher_is_better",
            "scope": "benchmark",
            "aggregation": (
                "mean"
                if name not in {"input_tokens", "output_tokens", "cost_usd"}
                else "sum"
            ),
            "sample_count": count,
        }
        for name, value in values.items()
    ]
    return metrics





def _duration_ms(value: Any) -> float | None:
    if not isinstance(value, Mapping):
        return None
    from datetime import datetime

    try:
        started = datetime.fromisoformat(str(value["started_at"]).replace("Z", "+00:00"))
        finished = datetime.fromisoformat(str(value["finished_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return None
    return max(0.0, (finished - started).total_seconds() * 1000)


def _integer(value: Any) -> int:
    return int(value) if _is_integer(value) else 0


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _load_object(path: Path) -> Mapping[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return _mapping(data, str(path))


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


__all__ = ["HARBOR_AGENT_IMPORT", "HarborBenchmarkAdapter", "parse_harbor_job_result"]
