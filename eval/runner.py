"""Run Harbor jobs and stream durable logs with bounded registry retries."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import socket
import time
import uuid
from typing import Any, Callable, Mapping
from .harbor.lifecycle import retire_containers, terminate_process
from .harbor.material import write_json

ProgressSink = Callable[[dict[str, Any]], None]


def run_harbor_job(
    command: list[str], *, environment: Mapping[str, str], timeout: int,
    job_root: Path, progress: ProgressSink | None, job_id: str,
    docker: str | None = None,
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
            job_id=job_id, log_offsets=log_offsets, docker=docker,
        )
        path = job_root / "harbor.log"
        text = path.read_text(encoding="utf-8", errors="replace")
        transient_registry_failure = (
            code != 0 and "Error getting dataset " in text
            and any(error in text for error in ("ConnectError", "ConnectTimeout", "ReadTimeout"))
            # Immutable Agent inputs may already be staged. Any other directory
            # can contain task/model side effects and therefore forbids replay.
            and not any(item.is_dir() and item.name != "artifacts" for item in job_root.iterdir())
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
    docker: str | None = None,
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
            env=dict(environment), start_new_session=True,
        )
        control = {"schema_version": 1, "token": uuid.uuid4().hex,
                   "state": "running", "hostname": socket.gethostname(),
                   "owner_pid": os.getpid(), "child_pid": process.pid,
                   "docker": docker, "job_id": job_id}
        started_at = time.monotonic()
        deadline = started_at + timeout
        next_update = started_at
        try:
            write_json(job_root / "control.json", control)
            while process.poll() is None:
                stop_path = job_root / "stop-request.json"
                if stop_path.is_file():
                    stop = json.loads(stop_path.read_text())
                    if stop.get("token") == control["token"]:
                        raise RuntimeError("Harbor evaluation stopped by request")
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
            cleanup: dict[str, Any] = {"state": "finished", "containers_removed": []}
            try:
                terminate_process(process)
                if docker is not None:
                    cleanup["containers_removed"] = retire_containers(job_root, docker, dict(environment))
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                cleanup.update(state="cleanup_failed", error=str(exc))
                raise RuntimeError("Harbor cleanup is unconfirmed; inspect cleanup.json") from exc
            finally:
                write_json(job_root / "cleanup.json", cleanup)
                write_json(job_root / "control.json", {**control, "state": cleanup["state"]})
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


