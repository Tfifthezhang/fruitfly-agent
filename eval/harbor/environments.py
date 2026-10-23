"""Prepare Agent and verifier environments through Harbor's public contracts."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shlex
import subprocess
from typing import Any
import uuid

from .dependencies import DEPENDENCY_TARGET, dependency_environment, dependency_mounts
from .docker import image_identity, run_container
from .host import HostConfig
from .material import digest, probe_command, runtime_mounts, tree_identity
from .lifecycle import retire_projects


PREPARED_ENVIRONMENT_IMPORT = "eval.harbor.docker_environment:PreparedDockerEnvironment"


def environment_key(task: dict[str, Any]) -> str:
    root = Path(task["path"])
    config = task["configuration"]
    return digest({"probe_contract": 2,
                   "configuration": {key: config.get(key) for key in ("environment", "agent", "verifier", "steps")},
                   "files": {name: tree_identity(root / name) if (root / name).exists() else None
                             for name in ("environment", "tests", "steps")}})


def environment_config(host: HostConfig, runtime: dict[str, Any]) -> dict[str, Any]:
    """Keep Agent mounts role-specific; factory kwargs reach both roles."""
    return {"type": "docker", "import_path": PREPARED_ENVIRONMENT_IMPORT,
            "mounts": runtime_mounts(runtime),
            "kwargs": {"dependency_mounts": dependency_mounts(host)},
            "env": {**dependency_environment(host), **host.setup_env}}


def environment_definitions(task: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve inheritance with Harbor, including each multi-step verifier."""
    from harbor.models.task.task import Task  # type: ignore[import-not-found, unused-ignore]
    from harbor.models.task.verifier_mode import resolve_effective_verifier_env_config  # type: ignore[import-not-found, unused-ignore]

    model = Task(task["path"])
    definitions = [{"role": "agent", "step": None, "context": str(model.paths.environment_dir),
                    "configuration": model.config.environment.model_dump(mode="json"),
                    "user": model.config.agent.user, "name": model.short_name}]
    for step in model.config.steps or (None,):
        config = resolve_effective_verifier_env_config(model.config, step)
        if config is None:
            continue
        context = model.paths.tests_dir
        user = model.config.verifier.user
        if step is not None:
            step_context = model.paths.step_tests_dir(step.name)
            if step_context.exists():
                context = step_context
            if step.verifier.user is not None:
                user = step.verifier.user
        model.paths.validate_input_tree(context)
        definitions.append({"role": "verifier", "step": step.name if step is not None else None,
                            "context": str(context), "configuration": config.model_dump(mode="json"),
                            "user": user, "name": model.short_name})
    return definitions


def dependency_probe(host: HostConfig) -> str:
    checks = ["set -eu", "test -d " + shlex.quote(DEPENDENCY_TARGET + "/assets")]
    for path in ("uv", "python", "pip"):
        cache = shlex.quote(DEPENDENCY_TARGET + "/cache/" + path)
        checks += ["mkdir -p " + cache, "fruitfly_probe_dir=$(mktemp -d " + cache + "/.probe.XXXXXX)",
                   'rmdir "$fruitfly_probe_dir"']
    for asset in host.assets:
        path = shlex.quote(DEPENDENCY_TARGET + "/assets/" + asset["path"])
        checks.append("test -r " + path)
        if asset.get("executable"):
            checks.append("test -x " + path)
    return "; ".join([*checks, "printf 'prepared dependencies accessible\\n'"])


def probe_environment(task: dict[str, Any], runtime: dict[str, Any], docker: str,
                      directory: Path, *, host: HostConfig) -> dict[str, Any]:
    probes = []
    settings = environment_config(host, runtime)
    for index, definition in enumerate(environment_definitions(task)):
        config = definition["configuration"]
        if config.get("os", "linux") != "linux":
            raise ValueError("prepared evaluation currently requires Linux Agent and verifier environments")
        target = directory / (str(index) + "-" + definition["role"])
        command = dependency_probe(host)
        env = dict(settings["env"])
        if definition["role"] == "agent":
            command += "; " + shlex.join(probe_command(runtime["python"]))
            env.update(runtime["environment"])
        else:
            env.update(host.verifier_env)
        context = Path(definition["context"])
        # Keep the network-free prebuilt Agent probe. Separate verifiers use
        # Harbor so their own resources and build contexts are exercised.
        if (definition["role"] == "agent" and config.get("docker_image")
                and not (context / "docker-compose.yaml").exists()):
            result = _probe_image(definition, runtime, docker, target, settings, command, env)
        else:
            result = asyncio.run(_probe_harbor(definition, docker, target, settings, command, env))
        probes.append({**definition, **result})
    images = {(image["reference"], image["id"]): image for probe in probes for image in probe["images"]}
    return {"environment_key": environment_key(task), "images": list(images.values()),
            "roles": probes, "detail": "Agent runtime and separate verifier dependency probes passed"}


def _probe_image(definition: dict[str, Any], runtime: dict[str, Any], docker: str,
                 directory: Path, settings: dict[str, Any], command: str, env: dict[str, str]) -> dict[str, Any]:
    image = definition["configuration"]["docker_image"]
    image_id = image_identity(docker, image)
    arguments = ["--network", "none"]
    if definition["user"] is not None:
        arguments += ["--user", str(definition["user"])]
    for mount in [*runtime_mounts(runtime), *settings["kwargs"]["dependency_mounts"]]:
        arguments += ["--mount", f"type=bind,src={mount['source']},dst={mount['target']}"
                      + (",readonly" if mount.get("read_only") else "")]
    for key, value in env.items():
        arguments += ["--env", f"{key}={value}"]
    arguments += ["--entrypoint", "/bin/sh", image_id, "-ec", command]
    result = run_container(docker, arguments, timeout=60)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "probe.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise ValueError(f"Agent environment probe failed; inspect {directory / 'probe.log'}")
    return {"images": [{"reference": image, "id": image_id}], "detail": result.stdout.strip()}


async def _probe_harbor(definition: dict[str, Any], docker: str, directory: Path,
                        settings: dict[str, Any], command: str, env: dict[str, str]) -> dict[str, Any]:
    from harbor.environments.factory import EnvironmentFactory  # type: ignore[import-not-found, unused-ignore]
    from harbor.models.task.config import EnvironmentConfig as TaskEnvironmentConfig  # type: ignore[import-not-found, unused-ignore]
    from harbor.models.trial.config import EnvironmentConfig  # type: ignore[import-not-found, unused-ignore]
    from harbor.models.trial.paths import TrialPaths  # type: ignore[import-not-found, unused-ignore]

    session = "fruitfly-check-" + uuid.uuid4().hex
    paths = TrialPaths(trial_dir=directory)
    paths.mkdir()
    paths.chmod_dir()
    config = TaskEnvironmentConfig.model_validate(definition["configuration"])
    mounts = settings["mounts"] if definition["role"] == "agent" else []
    environment = EnvironmentFactory.create_environment_from_config(
        config=EnvironmentConfig.model_validate(settings), environment_dir=Path(definition["context"]),
        environment_name=definition["name"], session_id=session, trial_paths=paths,
        task_env_config=config, mounts=mounts,
        network_policy=config.resolve_baseline(),
    )
    try:
        await asyncio.wait_for(environment.start(force_build=False), timeout=config.build_timeout_sec)
        result = await environment.exec(command=command, env=env, timeout_sec=60, user=definition["user"])
        (directory / "probe.log").write_text((result.stdout or "") + (result.stderr or ""), encoding="utf-8")
        if result.return_code:
            raise ValueError(f"{definition['role']} environment probe failed; inspect {directory / 'probe.log'}")
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
        return {"images": images, "detail": "Harbor environment startup and dependency probe passed"}
    finally:
        try:
            await asyncio.wait_for(environment.stop(delete=False), timeout=60)
        finally:
            retire_projects([session], docker, dict(os.environ))
