"""Resolve Harbor tasks once and preserve their contents outside SDK caches."""
from __future__ import annotations

import asyncio
from collections import Counter
import difflib
import json
from fnmatch import fnmatchcase
from pathlib import Path
import shutil
import tempfile
import tomllib
from typing import Any

from eval.benchmarks.base import BenchmarkDescriptor
from .host import HostConfig
from .material import digest, tree_identity, write_json


def task_name(path: Path) -> str:
    config = tomllib.loads((path / "task.toml").read_text(encoding="utf-8"))
    return config.get("task", {}).get("name") or path.name


async def registry_tasks(dataset: str, cache: Path, names: tuple[str, ...] = ()) -> list[tuple[str, Path]]:
    # Harbor is optional. Only preparation imports its public SDK; inspection,
    # report reading and ordinary Agent use work without it.
    try:
        from harbor.models.job.config import DatasetConfig  # type: ignore[import-not-found, unused-ignore]
        from harbor.tasks.client import TaskClient  # type: ignore[import-not-found, unused-ignore]
    except ImportError as exc:
        raise ValueError("task resolution requires the pinned Harbor benchmark extra") from exc
    name, separator, version = dataset.partition("@")
    configs = await DatasetConfig(name=name, version=version if separator else None,
                                  task_names=list(names) or None).get_task_configs()
    batch = await TaskClient().download_tasks([c.get_task_id() for c in configs], output_dir=cache)
    return [(config.get_task_id().get_name(), downloaded.path)
            for config, downloaded in zip(configs, batch.results, strict=True)]


def prepare_tasks(host: HostConfig, descriptor: BenchmarkDescriptor, variant: str) -> list[dict[str, Any]]:
    selection = next(v for v in descriptor.variants if v.variant_id == variant)
    if host.task_directory is not None:
        directory = host.task_directory
        if (directory / "task.toml").is_file():
            candidates = [(task_name(directory), directory)]
        else:
            candidates = [(task_name(p.parent), p.parent) for p in sorted(directory.glob("*/task.toml"))]
    else:
        candidates = asyncio.run(registry_tasks(descriptor.dataset, host.cache / "upstream", selection.task_names))
    selected = []
    for name, path in candidates:
        matches = [n for n in selection.task_names if n == name or n.rsplit("/", 1)[-1] == name]
        if selection.task_names and not matches:
            continue
        identity = matches[0] if len(matches) == 1 else name
        selected.append((identity, path))
    if (not selected or len({n for n, _ in selected}) != len(selected)
            or (selection.task_names and {n for n, _ in selected} != set(selection.task_names))):
        raise ValueError("resolved task set is empty, ambiguous or differs from the selected batch")
    names = [task_name(p) for _, p in selected]
    if len(set(names)) != len(names):
        raise ValueError("prepared local task names must be unique")
    result = []
    for identity, original in selected:
        task_hash = tree_identity(original)
        # A task may contain links to other files in its own tree. External
        # links would copy uncontrolled host material and are rejected.
        for link in original.rglob("*"):
            if link.is_symlink() and not link.resolve().is_relative_to(original.resolve()):
                raise ValueError(f"task contains an external link: {identity}/{link.relative_to(original)}")
        key = digest({"id": identity, "upstream": task_hash, "patches": host.task_patches})
        root = host.cache / "tasks" / key
        target = root / original.name
        patch_records = []
        if not target.exists():
            root.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".task-", dir=root.parent) as temporary:
                staged = Path(temporary) / "content"
                staged.mkdir()
                copied = staged / original.name
                shutil.copytree(original, copied, symlinks=False)
                for patch in host.task_patches:
                    if not fnmatchcase(identity, patch["task"]):
                        continue
                    file = copied / patch["path"]
                    before = file.read_text(encoding="utf-8")
                    if before.count(patch["old"]) != 1:
                        raise ValueError(f"task preparation patch did not match exactly once: {identity}/{patch['path']}")
                    after = before.replace(patch["old"], patch["new"], 1)
                    file.write_text(after, encoding="utf-8")
                    patch_records.append({"path": patch["path"], "diff": "".join(difflib.unified_diff(
                        before.splitlines(keepends=True), after.splitlines(keepends=True),
                        fromfile="upstream/" + patch["path"], tofile="prepared/" + patch["path"]))})
                write_json(staged / "identity.json", {"sha256": tree_identity(copied), "patches": patch_records})
                try:
                    staged.rename(root)
                except FileExistsError:
                    pass
        prepared = json.loads((target.parent / "identity.json").read_text())
        if tree_identity(target) != prepared["sha256"]:
            raise ValueError(f"prepared task contents changed: {identity}")
        config = tomllib.loads((target / "task.toml").read_text(encoding="utf-8"))
        result.append({"id": identity, "name": task_name(target), "path": str(target),
                       "sha256": prepared["sha256"], "image": config.get("environment", {}).get("docker_image"),
                       "original_sha256": task_hash, "patches": prepared["patches"],
                       "original": str(original), "configuration": config})
    return result


def check_tasks(tasks: list[dict[str, Any]]) -> None:
    for task in tasks:
        if tree_identity(Path(task["path"])) != task["sha256"]:
            raise ValueError(f"prepared task changed: {task['id']}; run eval prepare again")


def validate_coverage(tasks: list[dict[str, Any]], trials: list[dict[str, Any]], attempts: int) -> None:
    by_name = {task["name"]: task["id"] for task in tasks}
    for trial in trials:
        trial["task_id"] = by_name.get(trial["task_id"], trial["task_id"])
    expected = Counter({task["id"]: attempts for task in tasks})
    if Counter(t["task_id"] for t in trials) != expected:
        raise ValueError("Harbor results do not match the prepared task set and attempt count")


def preparation_key(descriptor: BenchmarkDescriptor, variant: str) -> str:
    selection = next(item for item in descriptor.variants if item.variant_id == variant)
    return digest({"dataset": descriptor.dataset, "version": descriptor.version,
                   "variant": variant, "task_names": selection.task_names})
