"""Inspect effective Harbor resources before pulling or starting environments."""
from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

import yaml

from .docker import image_identity
from .environments import environment_definitions


def task_requirements(task: dict[str, Any]) -> dict[str, Any]:
    """Use Harbor's resolved role/step definitions, including Compose services."""
    gpu: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    builds: list[dict[str, Any]] = []
    for definition in environment_definitions(task):
        owner = {"role": definition["role"], "step": definition["step"]}
        config = definition["configuration"]
        if config.get("gpus") or config.get("gpu_types"):
            gpu.append({**owner, "gpus": config.get("gpus"), "gpu_types": config.get("gpu_types", [])})
        context = Path(definition["context"])
        if config.get("docker_image"):
            images.append({**owner, "reference": config["docker_image"]})
        compose = context / "docker-compose.yaml"
        if not compose.is_file():
            if not config.get("docker_image"):
                builds.append({**owner, "context": str(context)})
            continue
        try:
            data = yaml.safe_load(compose.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid Compose definition: {compose}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("services"), dict):
            raise ValueError(f"Compose services must be a mapping: {compose}")
        # External fragments cannot establish absence of GPU requests locally.
        if data.get("include"):
            gpu.append({**owner, "detail": "external Compose include requires resource review"})
        for service, settings in data["services"].items():
            if not isinstance(settings, dict):
                raise ValueError(f"invalid Compose service: {compose}:{service}")
            entry = {**owner, "service": service}
            deploy = settings.get("deploy") or {}
            if not isinstance(deploy, dict):
                raise ValueError(f"invalid Compose deploy configuration: {compose}:{service}")
            resources = deploy.get("resources") or {}
            if not isinstance(resources, dict):
                raise ValueError(f"invalid Compose resources: {compose}:{service}")
            reservations = resources.get("reservations") or {}
            if not isinstance(reservations, dict):
                raise ValueError(f"invalid Compose reservations: {compose}:{service}")
            devices = reservations.get("devices") or []
            if not isinstance(devices, list) or not all(isinstance(d, dict) for d in devices):
                raise ValueError(f"invalid Compose device reservations: {compose}:{service}")
            if (settings.get("gpus") or settings.get("runtime") == "nvidia"
                    or settings.get("extends")
                    or any("/dev/nvidia" in str(d) for d in settings.get("devices", []))
                    or any(d.get("driver") == "nvidia" or "gpu" in d.get("capabilities", []) for d in devices)):
                gpu.append({**entry, "detail": "Compose GPU request or external service inheritance"})
            image = settings.get("image")
            if image:
                images.append({**entry, "reference": image})
            if settings.get("build"):
                builds.append({**entry, "context": str(context), "build": settings["build"]})
    return {"gpu_requirements": gpu, "images": images, "builds": builds}


def inspect_images(tasks: list[dict[str, Any]], docker: str) -> list[dict[str, Any]]:
    """Check full local references without pulling or mutating daemon state."""
    references = sorted({image["reference"] for task in tasks for image in task["requirements"]["images"]})
    result = []
    for reference in references:
        if "$" in reference:
            result.append({"reference": reference, "status": "unresolved", "detail": "Compose image requires runtime interpolation"})
            continue
        try:
            result.append({"reference": reference, "status": "cached", "image_id": image_identity(docker, reference)})
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            result.append({"reference": reference, "status": "unavailable", "detail": str(exc)})
    return result
