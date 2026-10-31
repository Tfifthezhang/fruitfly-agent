"""Evaluation-scoped stop requests and exact Docker container retirement."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import re
import socket
import subprocess
import time
from typing import Any

from .material import digest, write_json


def compose_project(session_id: str) -> str:
    """Normalize a recorded session using Docker Compose's project-name rules."""
    project = session_id.lower()
    if not re.match(r"^[a-z0-9]", project):
        project = "0" + project
    return re.sub(r"[^a-z0-9_-]", "-", project)


def record_environment(trial_dir: Path, session_id: str) -> None:
    """Keep exact environment ownership outside container-mounted log paths."""
    write_json(trial_dir / "fruitfly-environments" / (digest(session_id) + ".json"), {
        "trial_directory": str(trial_dir.resolve()), "session_id": session_id,
        "project": compose_project(session_id),
    })


def request_stop(evaluation: Path, *, wait_seconds: float = 20) -> dict[str, Any]:
    control = evaluation / "artifacts/harbor/control.json"
    if not control.is_file():
        raise ValueError("this evaluation has no active Harbor control record")
    state = json.loads(control.read_text())
    if state.get("hostname") != socket.gethostname():
        raise ValueError("stop must run on the evaluation host")
    if state.get("state") != "running":
        return {"state": state.get("state", "unknown"), "requested": False}
    write_json(control.with_name("stop-request.json"), {"requested_at": time.time(), "token": state["token"]})
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        current = json.loads(control.read_text())
        if current.get("state") != "running":
            return {"state": current["state"], "requested": True}
        try:
            os.kill(state["owner_pid"], 0)
        except ProcessLookupError:
            raise RuntimeError("evaluation owner is gone; cleanup cannot be confirmed from a stop request") from None
        time.sleep(.1)
    return {"state": "stop_requested", "requested": True,
            "detail": "cleanup is not confirmed; inspect control.json and cleanup.json"}


def terminate_process(process: subprocess.Popen, grace: float = 8) -> None:
    # The child has its own POSIX session. SIGINT lets Harbor cancel owned
    # trials and download logs before escalation. No name matching is involved.
    def send(sig: int) -> None:
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
    send(signal.SIGINT)
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        send(signal.SIGTERM)
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            send(signal.SIGKILL)
            process.wait()
    # A leader can exit while its Docker clients/workers remain alive. Waiting
    # only for that leader would repeat the original orphan-process failure.
    send(signal.SIGTERM)
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return
    time.sleep(.1)
    send(signal.SIGKILL)


def owned_projects(job_root: Path) -> list[str]:
    projects = set()
    for path in job_root.glob("*/*/config.json"):
        try:
            config = json.loads(path.read_text())
        except (OSError, ValueError):
            raise RuntimeError(f"cannot establish container ownership from {path}") from None
        name = config.get("trial_name")
        if isinstance(name, str) and name == path.parent.name:
            # Harbor Docker session_id is <trial_name>__env. Compose project
            # normalization is reflected by the actual label; require its exact
            # value and confirm the trial directory belongs to this evaluation.
            projects.add(compose_project(name + "__env"))
            for record in (path.parent / "fruitfly-environments").glob("*.json"):
                try:
                    value = json.loads(record.read_text())
                    session = value["session_id"]
                    if (not isinstance(session, str) or not session
                            or value["trial_directory"] != str(path.parent.resolve())
                            or value["project"] != compose_project(session)
                            or record.name != digest(session) + ".json"):
                        raise ValueError("environment ownership differs from trial")
                except (OSError, ValueError, KeyError, TypeError):
                    raise RuntimeError(f"cannot establish container ownership from {record}") from None
                projects.add(value["project"])
    return sorted(projects)


def owned_containers(job_root: Path, docker: str, environment: dict[str, str]) -> list[str]:
    return _project_containers(owned_projects(job_root), docker, environment)


def _project_containers(projects: list[str], docker: str, environment: dict[str, str]) -> list[str]:
    result = []
    for project in projects:
        proc = subprocess.run([docker, "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"],
                              env=environment, capture_output=True, text=True, timeout=10)
        if proc.returncode:
            raise RuntimeError("could not inspect evaluation-owned containers")
        result.extend(proc.stdout.split())
    return sorted(set(result))


def retire_containers(job_root: Path, docker: str, environment: dict[str, str]) -> list[str]:
    """Retire exact owned Compose resources, returning removed containers."""
    removed = retire_projects(owned_projects(job_root), docker, environment)
    write_json(job_root / "resources.json", removed)
    return removed["containers"]


def retire_projects(projects: list[str], docker: str, environment: dict[str, str]) -> dict[str, list[str]]:
    containers = _project_containers(projects, docker, environment)
    if containers:
        result = subprocess.run([docker, "rm", "-f", "-v", *containers], env=environment,
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError("evaluation container cleanup failed")
        if _project_containers(projects, docker, environment):
            raise RuntimeError("evaluation containers remain after cleanup")
    removed: dict[str, list[str]] = {"containers": containers, "networks": [], "volumes": []}
    for project in projects:
        for kind in ("network", "volume"):
            listed = subprocess.run([docker, kind, "ls", "-q", "--filter", f"label=com.docker.compose.project={project}"],
                                    env=environment, capture_output=True, text=True, timeout=10)
            if listed.returncode:
                raise RuntimeError(f"could not inspect evaluation-owned {kind}s")
            identifiers = listed.stdout.split()
            if identifiers:
                result = subprocess.run([docker, kind, "rm", *identifiers], env=environment,
                                        capture_output=True, text=True, timeout=30)
                if result.returncode:
                    raise RuntimeError(f"evaluation {kind} cleanup failed")
                removed[kind + "s"].extend(identifiers)
    return removed
