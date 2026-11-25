"""Harbor Docker extension adding prepared dependencies to every environment.

Loaded only by Harbor's public environment factory. Harbor retains ownership of
role-specific mounts, artifact transfer, resource policies and verification.
"""
from __future__ import annotations

from harbor.environments.docker.docker import DockerEnvironment  # type: ignore[import-not-found, unused-ignore]
from fruitfly_eval.backends.mounts import PreparedMounts


class PreparedDockerEnvironment(PreparedMounts, DockerEnvironment):
    """Append common mounts and record owned sessions through the shared contract."""
