"""Machine-local settings, independent of datasets and Agent configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

import yaml


def fields(value: object, allowed: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value) or set(value) - allowed:
        raise ValueError(f"invalid {label} fields; expected: {', '.join(sorted(allowed))}")
    return value


def text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError(f"{label} must be a nonempty single-line string")
    return value


def path_at(value: object, base: Path) -> Path:
    raw = os.path.expandvars(text(value, "path"))
    if "$" in raw:
        raise ValueError("path contains an unresolved environment variable")
    path = Path(raw).expanduser()
    return Path(os.path.abspath(path if path.is_absolute() else base / path))


def container_path(value: object, label: str) -> str:
    result = os.path.expandvars(text(value, label))
    if "$" in result or not PurePosixPath(result).is_absolute() or ".." in PurePosixPath(result).parts:
        raise ValueError(f"{label} must be an absolute container path without unresolved variables")
    return result


def environment(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("phase environment must be a mapping")
    result = {}
    for key, val in value.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError("invalid environment variable name")
        # Credentials retain the existing secret-environment path. Host settings
        # are copied to receipts, so they must never become another secret store.
        if re.search(r"(?:API_KEY|PASSWORD|SECRET|TOKEN|AUTHORIZATION)", key, re.I):
            raise ValueError("credentials belong in the existing secret environment")
        if key in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "LD_LIBRARY_PATH", "PYTHONDONTWRITEBYTECODE",
                   "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "PIP_CACHE_DIR", "UV_OFFLINE", "PIP_NO_INDEX"}:
            raise ValueError(f"{key} is owned by the prepared runtime/dependency settings")
        result[key] = text(val, "environment value")
        parsed = urlsplit(result[key])
        if parsed.scheme and (parsed.username or parsed.password or parsed.query):
            raise ValueError("phase URLs must not contain credentials or query strings")
    return result


@dataclass(frozen=True)
class Mount:
    source: Path
    target: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": "bind", "source": str(self.source), "target": self.target, "read_only": True}


@dataclass(frozen=True)
class HostConfig:
    path: Path
    cache: Path
    python: str
    mounts: tuple[Mount, ...]
    library_paths: tuple[str, ...] = ()
    setup_env: Mapping[str, str] = field(default_factory=dict)
    agent_env: Mapping[str, str] = field(default_factory=dict)
    verifier_env: Mapping[str, str] = field(default_factory=dict)
    assets: tuple[Mapping[str, Any], ...] = ()
    preparation: tuple[Mapping[str, Any], ...] = ()
    task_directory: Path | None = None
    uv: str | None = None
    offline: bool = False
    task_patches: tuple[Mapping[str, Any], ...] = ()

    @classmethod
    def read(cls, workspace: Path, explicit: str | Path | None = None) -> HostConfig:
        path = path_at(str(explicit), workspace) if explicit else workspace / ".fruitfly/eval-host.yaml"
        if not path.is_file():
            raise ValueError(f"Eval host configuration is missing: {path}; prepare .fruitfly/eval-host.yaml")
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            raise ValueError("invalid Eval host YAML") from None
        data = fields(loaded,
                      {"schema_version", "cache", "agent", "environment", "dependencies", "task_directory", "task_patches"}, "Eval host")
        if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise ValueError("Eval host configuration requires schema_version 1")
        base = path.parent
        agent = fields(data.get("agent", {}), {"python", "mounts", "library_paths"}, "agent runtime")
        python = container_path(agent.get("python"), "agent.python")
        if not PurePosixPath(python).is_absolute():
            raise ValueError("agent.python must be an absolute container path")
        mounts: list[Mount] = []
        def sequence(value: object, label: str) -> list[Any]:
            if not isinstance(value, list):
                raise ValueError(f"{label} must be a list")
            return value
        for item in sequence(agent.get("mounts", []), "agent.mounts"):
            row = fields(item, {"source", "target"}, "mount")
            source = path_at(row.get("source"), base)
            target = container_path(row.get("target", str(source)), "mount.target")
            if (not PurePosixPath(target).is_absolute() or target == "/"
                    or ".." in PurePosixPath(target).parts or "," in target or "," in str(source)):
                raise ValueError("mount targets must be absolute non-root paths")
            reserved = ("/installed-agent", "/logs", "/opt/fruitfly-eval-dependencies")
            if any(PurePosixPath(target).is_relative_to(p) or PurePosixPath(p).is_relative_to(target) for p in reserved):
                raise ValueError("runtime mounts overlap an Eval-owned container path")
            if any(PurePosixPath(target).is_relative_to(m.target) or PurePosixPath(m.target).is_relative_to(target) for m in mounts):
                raise ValueError("runtime mount targets must not overlap")
            mounts.append(Mount(source, target))
        if not mounts or len({m.target for m in mounts}) != len(mounts):
            raise ValueError("agent.mounts must contain distinct runtime mounts")
        if not any(PurePosixPath(python).is_relative_to(PurePosixPath(m.target)) for m in mounts):
            raise ValueError("agent.python must be covered by a runtime mount")
        libraries = tuple(container_path(p, "library path") for p in sequence(agent.get("library_paths", []), "library_paths"))
        if any(not PurePosixPath(p).is_absolute() for p in libraries):
            raise ValueError("library paths must be absolute container paths")
        if any(not any(PurePosixPath(p).is_relative_to(m.target) for m in mounts) for p in libraries):
            raise ValueError("agent.library_paths must be covered by runtime mounts")
        phases = fields(data.get("environment", {}), {"setup", "agent", "verifier"}, "phase environment")
        deps = fields(data.get("dependencies", {}), {"assets", "prepare", "uv", "offline"}, "dependencies")
        if type(deps.get("offline", False)) is not bool:
            raise ValueError("dependencies.offline must be boolean")
        assets = tuple(sequence(deps.get("assets", []), "assets"))
        for asset in assets:
            row = fields(asset, {"url", "path", "sha256", "executable"}, "dependency asset")
            if not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256", ""))):
                raise ValueError("dependency assets require an exact SHA-256")
            relative = PurePosixPath(text(row.get("path"), "asset.path"))
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("asset.path must stay inside the dependency store")
            text(row.get("url"), "asset.url")
            if type(row.get("executable", False)) is not bool:
                raise ValueError("asset.executable must be boolean")
        if len({a["path"] for a in assets}) != len(assets):
            raise ValueError("asset paths must be unique")
        recipes = tuple(sequence(deps.get("prepare", []), "dependencies.prepare"))
        for recipe in recipes:
            row = fields(recipe, {"image", "command"}, "dependency preparation")
            text(row.get("image"), "preparation.image")
            text(row.get("command"), "preparation.command")
        patches = tuple(sequence(data.get("task_patches", []), "task_patches"))
        for patch in patches:
            row = fields(patch, {"task", "path", "old", "new"}, "task patch")
            text(row.get("task"), "patch.task")
            relative = PurePosixPath(text(row.get("path"), "patch.path"))
            if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "tests":
                raise ValueError("task preparation patches must target a declared tests/ file")
            if not isinstance(row.get("old"), str) or not row["old"] or not isinstance(row.get("new"), str):
                raise ValueError("task patches require exact old/new text")
        uv = container_path(deps["uv"], "dependencies.uv") if deps.get("uv") else None
        if uv and (not PurePosixPath(uv).is_absolute() or ".." in PurePosixPath(uv).parts):
            raise ValueError("dependencies.uv must be an absolute container executable path")
        cache = path_at(data.get("cache", "eval-cache"), base)
        if any(cache.resolve().is_relative_to(m.source.resolve()) for m in mounts):
            raise ValueError("Eval cache must be outside all runtime mounts")
        return cls(path, cache, python, tuple(mounts), libraries,
                   environment(phases.get("setup", {})), environment(phases.get("agent", {})),
                   environment(phases.get("verifier", {})), assets, recipes,
                   path_at(data["task_directory"], base) if data.get("task_directory") else None,
                   uv,
                   deps.get("offline", False), patches)

    def runtime_env(self) -> dict[str, str]:
        values = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "/installed-agent/fruitfly/source"}
        if self.library_paths:
            values["LD_LIBRARY_PATH"] = ":".join(self.library_paths)
        return values

    def identity(self) -> dict[str, Any]:
        return {"python": self.python, "mounts": [m.to_dict() for m in self.mounts],
                "library_paths": list(self.library_paths), "setup": dict(self.setup_env),
                "agent": dict(self.agent_env), "verifier": dict(self.verifier_env),
                "uv": self.uv, "offline": self.offline, "task_patches": list(self.task_patches),
                "task_directory": str(self.task_directory) if self.task_directory else None,
                "resolved_task_directory": str(self.task_directory.resolve()) if self.task_directory else None}
