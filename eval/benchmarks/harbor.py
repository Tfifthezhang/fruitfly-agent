"""Harbor-backed benchmark adapter preserving the complete FruitFlyAgent harness."""

from __future__ import annotations

import json
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
        self, *, plan_path: Path, result_path: Path, variant: str,
        progress: ProgressSink | None = None,
    ) -> None:
        source_root = resolve_installation(
            os.environ.get("FRUITFLY_EVAL_PACKAGE"),
            checkout=Path(__file__).resolve().parents[2],
        )
        preflight = self.preflight(variant)
        if not preflight.available:
            failed = next(item for item in preflight.checks if not item["ok"])
            raise RuntimeError(str(failed["detail"]))
        plan = _load_object(plan_path)
        request = _mapping(plan.get("request"), "plan.request")
        runtime = _mapping(request.get("runtime"), "plan.request.runtime")
        execution = _mapping(request.get("execution"), "plan.request.execution")
        reproducibility = _mapping(
            plan.get("reproducibility"), "plan.reproducibility"
        )
        conditions = plan.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            raise ValueError("plan.conditions must be a non-empty list")

        timeout = int(execution.get("timeout_seconds", 3600))
        jobs_root = result_path.parent / "harbor"
        jobs_root.mkdir(parents=True, exist_ok=True)
        workspace_paths = WorkspacePaths(Path(str(runtime.get("working_directory", ""))))
        for notice in workspace_paths.notices():
            print(f"notice: {notice}", file=sys.stderr)
        runner_environment = {**load_env(workspace_paths.secret_file()), **os.environ}
        all_trials: list[dict[str, Any]] = []
        all_metrics: list[dict[str, Any]] = []
        artifacts: list[dict[str, Any]] = []
        for condition_index, condition in enumerate(conditions, 1):
            condition = _mapping(condition, "plan condition")
            condition_id = str(condition.get("condition_id", ""))
            if not condition_id:
                raise ValueError("plan condition has no condition_id")
            condition_root = jobs_root / condition_id
            condition_root.mkdir(parents=True, exist_ok=True)
            config_path, model_catalog, secret_names = _condition_runtime_files(
                runtime=runtime,
                condition=condition,
                output_dir=condition_root,
            )
            job_name = f"{self.descriptor.benchmark_id}-{condition_id}"
            command = self._command(
                executable=preflight.command[0],
                dataset=self.descriptor.dataset,
                variant=variant,
                execution=execution,
                jobs_dir=condition_root,
                job_name=job_name,
                source_root=source_root,
                config_path=config_path,
                model_catalog=model_catalog,
                profile=str(runtime.get("profile")),
                secret_names=secret_names,
            )
            if progress is not None:
                progress({
                    "type": "job_started", "condition_id": condition_id,
                    "condition_index": condition_index, "condition_total": len(conditions),
                    "artifacts_path": str(condition_root),
                })
            returncode, detail = _run_harbor_job(
                command, environment=runner_environment,
                timeout=timeout, condition_root=condition_root,
                progress=progress, condition_id=condition_id,
            )
            if returncode != 0:
                raise RuntimeError(
                    f"Harbor exited with {returncode}"
                    + (f": {detail[-2000:]}" if detail else "")
                    + f"\nFull runner log: {condition_root / 'harbor.log'}"
                )
            job_dir = condition_root / job_name
            job_result_path = job_dir / "result.json"
            if not job_result_path.is_file():
                candidates = tuple(condition_root.glob("*/result.json"))
                if len(candidates) != 1:
                    raise RuntimeError("Harbor did not create a unique job result")
                job_result_path = candidates[0]
                job_dir = job_result_path.parent
            trials, metrics = parse_harbor_job_result(
                _load_harbor_job_result(job_result_path),
                condition_id=condition_id,
                expected_manifest_digest=(
                    str(reproducibility.get("runtime_manifest_digest"))
                    if not condition.get("mechanism_overrides")
                    else None
                ),
            )
            all_trials.extend(trials)
            all_metrics.extend(metrics)
            artifacts.append({"kind": "harbor_job", "path": str(job_dir)})
            artifacts.append({"kind": "harbor_log", "path": str(condition_root / "harbor.log")})
            if progress is not None:
                progress({
                    "type": "job_finished", "condition_id": condition_id,
                    "completed": len(all_trials),
                    "total": len(all_trials) if variant == "smoke" else None,
                })

        payload = {
            "schema_version": 1,
            "status": "completed",
            "metrics": all_metrics,
            "comparisons": _comparisons(all_metrics),
            "errors": {},
            "artifacts": artifacts,
            "trials": all_trials,
        }
        result_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

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
        if variant == "smoke":
            if not self.descriptor.smoke_task:
                raise ValueError(
                    f"{self.descriptor.benchmark_id} does not declare a smoke task"
                )
            command.extend(("--include-task-name", self.descriptor.smoke_task))
            command.extend(("--n-tasks", "1"))
        return command


def _run_harbor_job(
    command: list[str], *, environment: Mapping[str, str], timeout: int,
    condition_root: Path, progress: ProgressSink | None, condition_id: str,
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
            condition_root=condition_root, progress=progress,
            condition_id=condition_id, log_offsets=log_offsets,
        )
        path = condition_root / "harbor.log"
        text = path.read_text(encoding="utf-8", errors="replace")
        transient_registry_failure = (
            code != 0 and "Error getting dataset " in text
            and any(error in text for error in ("ConnectError", "ConnectTimeout", "ReadTimeout"))
            # Harbor creates its job directory after dataset resolution. Once
            # any directory exists, model/task side effects cannot be ruled out.
            and not any(item.is_dir() for item in condition_root.iterdir())
        )
        if not transient_registry_failure or attempt == 3 or deadline - time.monotonic() <= 1:
            return code, detail
        archive = condition_root / f"harbor-attempt-{attempt}.log"
        path.replace(archive)
        log_offsets[archive] = archive.stat().st_size
        log_offsets.pop(path, None)
        if progress is not None:
            progress({
                "type": "log", "condition_id": condition_id, "source": "registry",
                "text": f"Registry connection failed before job creation; retry {attempt + 1}/3. Previous output: {archive.name}\n",
            })
        time.sleep(1)
    raise AssertionError("unreachable")


def _run_harbor_job_once(
    command: list[str], *, environment: Mapping[str, str], timeout: int,
    condition_root: Path, progress: ProgressSink | None, condition_id: str,
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
    output_path = condition_root / "harbor.log"
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
                        condition_root, condition_id, offsets, fragments, observe
                    )
                    _forward_trial_results(
                        condition_root, condition_id, finished_trials, observe
                    )
                    _forward_logs(condition_root, condition_id, log_offsets, log_fragments, progress)
                    now = time.monotonic()
                    if now >= next_update:
                        progress({
                            "type": "job_progress", "condition_id": condition_id,
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
                    condition_root, condition_id, offsets, fragments, observe
                )
                _forward_trial_results(
                    condition_root, condition_id, finished_trials, observe
                )
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if progress is not None:
                _forward_logs(
                    condition_root, condition_id, log_offsets, log_fragments,
                    progress, final=True,
                )
            # Archive the complete event stream for post-run inspection.
            for path in condition_root.glob("*/*/agent/live-events.jsonl"):
                path.replace(path.with_name("events.jsonl"))
        output.seek(0, os.SEEK_END)
        output.seek(max(0, output.tell() - 4000))
        return process.returncode, output.read().decode("utf-8", errors="replace").strip()


def _forward_logs(
    condition_root: Path, condition_id: str,
    offsets: dict[Path, int], fragments: dict[Path, bytes],
    progress: ProgressSink, *, final: bool = False,
) -> None:
    """Tail durable runner/setup/verifier logs, including partial final lines."""

    paths = {condition_root / "harbor.log"}
    paths.update(condition_root.rglob("*.log"))
    paths.update(condition_root.rglob("exception.txt"))
    paths.update(condition_root.glob("*/*/verifier/*.txt"))
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
                "type": "log", "condition_id": condition_id,
                "source": str(path.relative_to(condition_root)),
                "text": text[start:start + 4096],
            })


def _forward_agent_events(
    condition_root: Path, condition_id: str,
    offsets: dict[Path, int], fragments: dict[Path, bytes],
    progress: ProgressSink,
) -> None:
    for path in condition_root.glob("*/*/agent/live-events.jsonl"):
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
                    "type": "agent_event", "condition_id": condition_id,
                    "trial_id": path.parent.parent.name, "event": event,
                })


def _forward_trial_results(
    condition_root: Path, condition_id: str,
    seen: set[Path], progress: ProgressSink,
) -> None:
    for path in condition_root.glob("*/*/result.json"):
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
            "type": "trial_finished", "condition_id": condition_id,
            "trial_id": path.parent.name, "completed": len(seen),
            "error": value.get("exception_info"),
        })


def _condition_runtime_files(
    *,
    runtime: Mapping[str, Any],
    condition: Mapping[str, Any],
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
    overrides = _mapping(condition.get("mechanism_overrides", {}), "mechanism overrides")
    adjusted_mechanisms: list[dict[str, Any]] = []
    for raw_item in mechanisms:
        if not isinstance(raw_item, Mapping) or not isinstance(raw_item.get("id"), str):
            raise ValueError("harness mechanism selections must have a string id")
        item = dict(raw_item)
        mechanism_id = item["id"]
        if mechanism_id in overrides:
            override = _mapping(overrides[mechanism_id], "mechanism override")
            item["enabled"] = bool(override.get("enabled", item.get("enabled", True)))
        adjusted_mechanisms.append(item)
    remote_catalog = "/installed-agent/fruitfly/runtime/models.yaml"
    adjusted_profile = dict(profile)
    adjusted_model = dict(model)
    adjusted_model["catalog"] = remote_catalog
    adjusted_profile["model"] = adjusted_model
    adjusted_profile["mechanisms"] = adjusted_mechanisms
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
    condition_id: str,
    expected_manifest_digest: str | None = None,
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
        verifier = trial.get("verifier_result")
        reward_map = (
            verifier.get("rewards")
            if isinstance(verifier, Mapping)
            and isinstance(verifier.get("rewards"), Mapping)
            else {}
        )
        numeric_rewards = [
            float(value)
            for value in reward_map.values()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        reward = (
            float(reward_map["reward"])
            if isinstance(reward_map.get("reward"), (int, float))
            else (numeric_rewards[0] if len(numeric_rewards) == 1 else None)
        )
        agent_result = trial.get("agent_result")
        metadata = (
            agent_result.get("metadata") if isinstance(agent_result, Mapping) else None
        )
        actual_manifest_digest = (
            metadata.get("runtime_manifest_digest")
            if isinstance(metadata, Mapping)
            else None
        )
        manifest_mismatch = (
            expected_manifest_digest is not None
            and actual_manifest_digest != expected_manifest_digest
        )
        if isinstance(exception, Mapping):
            errors += 1
            exception_type = str(exception.get("exception_type", ""))
            if "timeout" in exception_type.lower():
                timeouts += 1
            error = {
                "type": exception_type or "HarborTrialError",
                "message": str(exception.get("exception_message", "")),
            }
            status = "error"
        elif manifest_mismatch:
            errors += 1
            error = {
                "type": "RuntimeManifestMismatch",
                "message": (
                    "Harbor trial did not run the frozen FruitFlyAgent runtime "
                    f"({actual_manifest_digest!r} != {expected_manifest_digest!r})"
                ),
            }
            status = "error"
        else:
            error = None
            status = "passed" if reward is not None and reward >= 1.0 else "failed"
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
                "trial_id": str(trial.get("id") or f"{condition_id}-{index}"),
                "condition_id": condition_id,
                "task_id": task_id,
                "status": status,
                "metrics": metrics,
                "error": error,
                "state_policy": "clean",
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
            "condition_id": condition_id,
            "aggregation": (
                "mean"
                if name not in {"input_tokens", "output_tokens", "cost_usd"}
                else "sum"
            ),
            "sample_count": count,
        }
        for name, value in values.items()
    ]
    return trials, metrics


def _comparisons(metrics: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_condition = {
        (str(item.get("condition_id")), str(item.get("name"))): item.get("value")
        for item in metrics
    }
    comparisons = []
    names = {name for condition, name in by_condition if condition == "candidate"}
    for name in sorted(names):
        baseline = by_condition.get(("baseline", name))
        candidate = by_condition.get(("candidate", name))
        if isinstance(baseline, (int, float)) and isinstance(candidate, (int, float)):
            comparisons.append(
                {
                    "metric": name,
                    "baseline": baseline,
                    "candidate": candidate,
                    "delta": candidate - baseline,
                }
            )
    return comparisons


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
