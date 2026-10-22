"""Explicit dependency assets and repeatable container cache-warming recipes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import tempfile
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx

from .host import HostConfig
from .material import digest, write_json
from .docker import run_container
from .environments import image_identity


DEPENDENCY_TARGET = "/opt/fruitfly-eval-dependencies"


def dependency_environment(host: HostConfig) -> dict[str, str]:
    values = {"UV_CACHE_DIR": DEPENDENCY_TARGET + "/cache/uv",
              "UV_PYTHON_INSTALL_DIR": DEPENDENCY_TARGET + "/cache/python",
              "PIP_CACHE_DIR": DEPENDENCY_TARGET + "/cache/pip"}
    if host.offline:
        values["UV_OFFLINE"] = "1"
        values["PIP_NO_INDEX"] = "1"
    if host.uv:
        values["PATH"] = str(PurePosixPath(host.uv).parent) + ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    return values


def prepare_dependencies(host: HostConfig, docker: str) -> dict[str, Any]:
    root = host.cache / "dependencies"
    root.mkdir(parents=True, exist_ok=True)
    (root / "cache").mkdir(exist_ok=True)
    (root / "assets").mkdir(exist_ok=True)
    assets = []
    for asset in host.assets:
        target = root / "assets" / asset["path"]
        if not target.resolve().is_relative_to((root / "assets").resolve()):
            raise ValueError("dependency asset path escapes its store")
        url = urlsplit(asset["url"])
        if url.scheme not in {"https", "file"} or url.username or url.password or url.query:
            raise ValueError("dependency URLs must be credential-free HTTPS or local file URLs")
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != asset["sha256"]:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                temporary = Path(handle.name)
                try:
                    if url.scheme == "file":
                        with Path(unquote(url.path)).open("rb") as source:
                            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                                handle.write(chunk)
                    else:
                        with httpx.stream("GET", asset["url"], follow_redirects=True, timeout=30) as response:
                            response.raise_for_status()
                            for chunk in response.iter_bytes():
                                handle.write(chunk)
                    handle.flush()
                    if hashlib.sha256(temporary.read_bytes()).hexdigest() != asset["sha256"]:
                        raise ValueError(f"dependency checksum mismatch: {asset['path']}")
                    temporary.replace(target)
                except httpx.HTTPError:
                    raise ValueError(f"dependency download failed: {asset['path']}; verify its configured URL and host network") from None
                finally:
                    temporary.unlink(missing_ok=True)
        if asset.get("executable"):
            target.chmod(0o755)
        assets.append({"path": asset["path"], "sha256": asset["sha256"]})
    if host.uv:
        expected = DEPENDENCY_TARGET + "/assets/"
        if (not host.uv.startswith(expected) or not any(
                host.uv == expected + a["path"] and a.get("executable") for a in host.assets)):
            raise ValueError("dependencies.uv must name a declared executable asset under " + expected)
    images = {r["image"]: image_identity(docker, r["image"]) for r in host.preparation}
    recipe_key = digest({"assets": assets, "recipes": host.preparation, "images": images,
                         "environment": dict(host.verifier_env), "uv": host.uv})
    receipt_path = root / "prepared.json"
    previous = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
    if previous.get("id") != recipe_key:
        for index, recipe in enumerate(host.preparation):
            # Preparation may download. It never runs the Agent or the scoring
            # assertions. Exact commands and logs remain inspectable.
            command = []
            for mount in dependency_mounts(host):
                command += ["--mount", f"type=bind,src={mount['source']},dst={mount['target']}"
                            + (",readonly" if mount.get("read_only") else "")]
            env = {**dependency_environment(host), **host.verifier_env}
            env.pop("UV_OFFLINE", None)
            env.pop("PIP_NO_INDEX", None)
            for key, value in env.items():
                command += ["--env", f"{key}={value}"]
            command += ["--entrypoint", "/bin/sh", images[recipe["image"]], "-ec", recipe["command"]]
            completed = run_container(docker, command, log=root / f"prepare-{index}.log", timeout=1800)
            if completed.returncode:
                raise ValueError(f"dependency preparation failed; inspect {root / f'prepare-{index}.log'}")
    result = {"schema_version": 1, "id": recipe_key, "assets": assets,
              "recipes": list(host.preparation), "images": images, "offline": host.offline,
              "verifier_execution": "unverified until a complete smoke trial",
              "remaining_network": ["apt, curl and task-specific downloads are not covered by uv/pip offline flags"]}
    write_json(receipt_path, result)
    return result


def check_dependencies(host: HostConfig, receipt: dict[str, Any]) -> None:
    if receipt.get("offline") != host.offline or receipt.get("recipes") != list(host.preparation):
        raise ValueError("dependency settings changed; run eval prepare again")
    expected = [{"path": a["path"], "sha256": a["sha256"]} for a in host.assets]
    if receipt.get("assets") != expected:
        raise ValueError("dependency assets changed; run eval prepare again")
    for asset in expected:
        path = host.cache / "dependencies/assets" / asset["path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]:
            raise ValueError(f"prepared dependency is missing or changed: {asset['path']}")


def dependency_mounts(host: HostConfig) -> list[dict[str, Any]]:
    # Only package download/build caches are writable and shared. Agent code and
    # environments stay read-only; task files and installed task packages remain
    # per-container. uv/pip own the concurrency locks for their caches.
    return [
        {"type": "bind", "source": str(host.cache / "dependencies/assets"),
         "target": DEPENDENCY_TARGET + "/assets", "read_only": True},
        {"type": "bind", "source": str(host.cache / "dependencies/cache"),
         "target": DEPENDENCY_TARGET + "/cache"},
    ]
