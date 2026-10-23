"""Harbor Docker extension adding prepared dependencies to every environment.

Loaded only by Harbor's public environment factory. Harbor retains ownership of
role-specific mounts, artifact transfer, resource policies and verification.
"""
from __future__ import annotations

from typing import Any

from harbor.environments.docker.docker import DockerEnvironment  # type: ignore[import-not-found, unused-ignore]
from harbor.models.trial.config import ServiceVolumeConfig  # type: ignore[import-not-found, unused-ignore]

from .lifecycle import record_environment


class PreparedDockerEnvironment(DockerEnvironment):
    """Append common dependency mounts without inferring the environment role."""

    def __init__(self, *args: Any, dependency_mounts: list[ServiceVolumeConfig],
                 mounts: list[ServiceVolumeConfig] | None = None, **kwargs: Any) -> None:
        combined = list(mounts or [])
        targets = {mount["target"] for mount in combined}
        for definition in dependency_mounts:
            target = definition["target"]
            if target in targets:
                raise ValueError(f"prepared dependency mount conflicts with Harbor mount: {target}")
            targets.add(target)
            combined.append(definition.copy())
        # Record the exact session before starting resources. This includes
        # separate verifiers and Harbor's shortened multi-step session names.
        record_environment(kwargs["trial_paths"].trial_dir, kwargs["session_id"])
        super().__init__(*args, mounts=combined, **kwargs)
