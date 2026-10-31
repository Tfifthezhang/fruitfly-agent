"""Short-lived, uniquely named preparation containers with bounded cleanup."""
from __future__ import annotations

from pathlib import Path
import subprocess
import uuid


def image_identity(docker: str, image: str) -> str:
    result = subprocess.run([docker, "image", "inspect", image, "--format", "{{.Id}}"],
                            capture_output=True, text=True, timeout=15)
    if result.returncode or not result.stdout.strip():
        raise ValueError(f"image is not cached: {image}; check never pulls images")
    return result.stdout.strip()


def run_container(docker: str, arguments: list[str], *, timeout: int,
                  log: Path | None = None) -> subprocess.CompletedProcess[str]:
    name = "fruitfly-prepare-" + uuid.uuid4().hex
    command = [docker, "run", "--name", name, "--pull=never", *arguments]
    try:
        if log is None:
            return subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        with log.open("w", encoding="utf-8") as output:
            return subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    finally:
        # Killing the Docker CLI alone does not stop the container it started.
        removed = subprocess.run([docker, "rm", "-f", "-v", name], capture_output=True, text=True, timeout=30)
        if removed.returncode:
            remaining = subprocess.run([docker, "ps", "-aq", "--filter", f"name=^/{name}$"],
                                       capture_output=True, text=True, timeout=10)
            if remaining.returncode or remaining.stdout.strip():
                raise RuntimeError(f"preparation container cleanup unconfirmed: {name}")
