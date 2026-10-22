"""Probe declared environments through Docker or Harbor's public factory."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shlex
import subprocess
from typing import Any
import uuid

from .docker import run_container
from .material import digest, probe_command, runtime_mounts, tree_identity
from .lifecycle import retire_projects


def environment_key(task: dict[str, Any]) -> str:
    directory = Path(task["path"]) / "environment"
    return digest({"configuration": task["configuration"].get("environment", {}),
                   "agent_user": task["configuration"].get("agent", {}).get("user"),
                   "files": tree_identity(directory) if directory.exists() else None})


def image_identity(docker: str, image: str) -> str:
    result = subprocess.run([docker, "image", "inspect", image, "--format", "{{.Id}}"],
                            capture_output=True, text=True, timeout=15)
    if result.returncode or not result.stdout.strip():
        raise ValueError(f"image is not cached: {image}; check never pulls images")
    return result.stdout.strip()


def probe_environment(task: dict[str, Any], runtime: dict[str, Any], docker: str,
                      directory: Path) -> dict[str, Any]:
    if task["configuration"].get("environment", {}).get("os", "linux") != "linux":
        raise ValueError("prepared Agent supervision currently requires Linux task environments")
    # Compose tasks can override the main image and add services. Use Harbor to
    # construct those environments instead of guessing from docker_image alone.
    compose = Path(task["path"]) / "environment/docker-compose.yaml"
    if not task["image"] or compose.exists():
        return asyncio.run(_probe_harbor(task, runtime, docker, directory))
    image_id = image_identity(docker, task["image"])
    arguments = ["--network", "none"]
    user = task["configuration"].get("agent", {}).get("user")
    if user is not None:
        arguments += ["--user", str(user)]
    for mount in runtime_mounts(runtime):
        arguments += ["--mount", f"type=bind,src={mount['source']},dst={mount['target']},readonly"]
    for key, value in runtime["environment"].items():
        arguments += ["--env", f"{key}={value}"]
    probe = probe_command(runtime["python"])
    arguments += ["--entrypoint", probe[0], image_id, *probe[1:]]
    result = run_container(docker, arguments, timeout=60)
    if result.returncode:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "probe.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        raise ValueError(f"runtime probe failed for {task['id']}; inspect {directory / 'probe.log'}")
    return {"environment_key": environment_key(task), "images": [{"reference": task["image"], "id": image_id}],
            "detail": result.stdout.strip()}


async def _probe_harbor(task: dict[str, Any], runtime: dict[str, Any], docker: str,
                        directory: Path) -> dict[str, Any]:
    from harbor.environments.factory import EnvironmentFactory  # type: ignore[import-not-found, unused-ignore]
    from harbor.models.task.task import Task  # type: ignore[import-not-found, unused-ignore]
    from harbor.models.trial.config import EnvironmentConfig  # type: ignore[import-not-found, unused-ignore]
    from harbor.models.trial.paths import TrialPaths  # type: ignore[import-not-found, unused-ignore]

    model = Task(task["path"])
    session = "fruitfly-check-" + uuid.uuid4().hex
    paths = TrialPaths(trial_dir=directory)
    paths.mkdir()
    paths.chmod_dir()
    environment = EnvironmentFactory.create_environment_from_config(
        config=EnvironmentConfig.model_validate({"type": "docker", "mounts": runtime_mounts(runtime)}),
        environment_dir=model.paths.environment_dir, environment_name=model.short_name,
        session_id=session, trial_paths=paths, task_env_config=model.config.environment,
    )
    try:
        await asyncio.wait_for(environment.start(force_build=False), timeout=model.config.environment.build_timeout_sec)
        result = await environment.exec(command=shlex.join(probe_command(runtime["python"])),
                                        env=runtime["environment"], timeout_sec=60,
                                        user=task["configuration"].get("agent", {}).get("user"))
        (directory / "probe.log").write_text((result.stdout or "") + (result.stderr or ""), encoding="utf-8")
        if result.return_code:
            raise ValueError(f"runtime probe failed for {task['id']}; inspect {directory / 'probe.log'}")
        containers = subprocess.run([docker, "ps", "-aq", "--filter", f"label=com.docker.compose.project={session}"],
                                    capture_output=True, text=True, timeout=15)
        if containers.returncode or not containers.stdout.split():
            raise ValueError("could not record prepared environment images")
        images = []
        for container in containers.stdout.split():
            result_image = subprocess.run([docker, "inspect", container, "--format", "{{.Config.Image}} {{.Image}}"],
                                          capture_output=True, text=True, timeout=15)
            if result_image.returncode or len(result_image.stdout.split()) != 2:
                raise ValueError("could not record prepared environment image identity")
            reference, image_id = result_image.stdout.split()
            images.append({"reference": reference, "id": image_id})
        return {"environment_key": environment_key(task), "images": images,
                "detail": "Harbor environment startup and runtime probe passed"}
    finally:
        try:
            # Preserve prepared build images. Harbor's delete=True can request
            # image removal; our scoped retirement removes only live resources.
            await asyncio.wait_for(environment.stop(delete=False), timeout=60)
        finally:
            retire_projects([session], docker, dict(os.environ))
