"""Discover task packages, freeze comparison suites and edit authorized training data."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
import tempfile
from uuid import uuid4
from typing import Iterator, Sequence
from fruitfly_agent.improvement.contracts.tasks import TaskCase
from fruitfly_agent.lab.improvement.assessment.scorers.policies import TaskPolicy, builtin_task_policies, task_policy
from .packages import (PackageMaterial, digest, encoded, readable_json, input_key, safe_path,
    read_bytes, validate_acceptance, validate_pack, package_documents, partition_cases, load_pack)

@dataclass(frozen=True)
class TaskPackRegistration:
    path: Path
    writable: bool = False


@dataclass(frozen=True)
class TaskPackSummary:
    pack_id: str
    name: str
    source_hash: str = ""
    description: str = ""
    train_count: int = 0
    validation_count: int = 0
    holdout_count: int = 0
    writable: bool = False
    error: str = ""
    default_direction: str = ""
    acceptance_example: str = ""


@dataclass(frozen=True)
class FrozenTaskSuite:
    train: tuple[TaskCase, ...]
    validation: tuple[TaskCase, ...]
    digest: str
    pack_id: str
    name: str
    source_hash: str
    target_id: str
    policy_id: str = "normalized-exact-v1"
    case_sources: tuple[tuple[str, str], ...] = ()
    execution_id: str = "normalized-exact-v1"
    evaluation_policy: object = None
    material_files: tuple[tuple[str, str], ...] = ()
    case_ids: tuple[tuple[str, str], ...] = ()
    direction: str = 'max'


class TaskPackCatalog:
    """Workspace catalog; no models, no runtime configuration or adoption rights."""
    def __init__(
        self, workspace: Path, registrations: Sequence[TaskPackRegistration] = (), *,
        policies: Sequence[TaskPolicy] | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.root = self.workspace / ".fruitfly/improvement/task-packs"
        self.registrations = tuple(registrations)
        self.policies = tuple(builtin_task_policies() if policies is None else policies)

    def _sources(self) -> list[tuple[Path, bool]]:
        sources = []
        roots = (TaskPackRegistration(self.root, True), *self.registrations)
        for registration in roots:
            path = safe_path(self.workspace, Path(registration.path))
            if path.is_file() or path.is_symlink():
                sources.append((path, registration.writable))
            elif path.exists():
                for directory in path.iterdir():
                    if directory.name.startswith(".") or not directory.is_dir():
                        continue
                    source = directory / "pack.json"
                    # Python 3.11 glob omits dangling literal-name symlinks.
                    # Keep them visible so loading reports the invalid path.
                    if not source.exists() and not source.is_symlink():
                        continue
                    sources.append((source, registration.writable))
                    if len(sources) > 100:
                        raise ValueError("task package catalog exceeds 100 sources")
        if len(sources) > 100:
            raise ValueError("task package catalog exceeds 100 sources")
        # A repeated registration of the same file is an error, not a privilege upgrade.
        if len({str(p) for p, _ in sources}) != len(sources):
            raise ValueError("duplicate task package source registration")
        return sources

    def _read(self, path: Path) -> tuple[PackageMaterial, str]:
        loaded = load_pack(self.workspace, path, policies=self.policies)
        return loaded.material, loaded.source_hash

    def summaries(self, target_id: str | None = None) -> tuple[TaskPackSummary, ...]:
        summaries = []
        for path, writable in self._sources():
            try:
                payload, identity = self._read(path)
                error = "" if payload["train"] and payload["validation"] else "needs both training and independent validation cases"
                if target_id and target_id not in payload["compatible_targets"]:
                    error = "task package does not support the active target"
                summaries.append(TaskPackSummary(payload["id"], payload["name"], identity,
                    payload.get("description", ""), len(payload["train"]), len(payload["validation"]),
                    len(payload.get("holdout", [])), writable, error, payload.get("default_direction", ""),
                    task_policy(payload["objective"]["policy_id"], policies=self.policies).acceptance_example))
            except (OSError, ValueError, TypeError) as exc:
                summaries.append(TaskPackSummary("invalid-" + digest(str(path).encode())[7:19], path.parent.name, error=str(exc)))
        ids = [s.pack_id for s in summaries]
        summaries = [TaskPackSummary(**{**s.__dict__, "error": "duplicate task package id"}) if ids.count(s.pack_id) > 1 else s for s in summaries]
        return tuple(sorted(summaries, key=lambda s: (bool(s.error), s.name, s.pack_id)))

    def _locate(self, pack_id: str) -> tuple[Path, bool, PackageMaterial, str]:
        found = []
        for path, writable in self._sources():
            try:
                payload, identity = self._read(path)
            except (OSError, ValueError, TypeError):
                continue
            if payload["id"] == pack_id:
                found.append((path, writable, payload, identity))
        if len(found) != 1:
            raise ValueError("unknown or duplicate task package id")
        return found[0]

    def compatible_targets(self, pack_id: str) -> tuple[str, ...]:
        """Public material scope; no private acceptance content."""
        return tuple(self._locate(pack_id)[2]['compatible_targets'])

    def source_hash(self, pack_id: str) -> str:
        return self._locate(pack_id)[3]

    def freeze(self, pack_id: str, target_id: str) -> FrozenTaskSuite:
        path, _, payload, identity = self._locate(pack_id)
        loaded = load_pack(self.workspace, path, policies=self.policies)
        if loaded.source_hash != identity:
            raise ValueError("task package changed while freezing; reload")
        if target_id not in payload["compatible_targets"]:
            raise ValueError("task package does not support the active target")
        if not payload["train"] or not payload["validation"]:
            raise ValueError("need independent validation and training cases before improvement")
        policy = task_policy(payload["objective"]["policy_id"], policies=self.policies)
        policy.check_available()
        projection = {p: [policy.project(c).__dict__ for c in partition_cases(payload, p)] for p in ("train", "validation")}
        return FrozenTaskSuite(tuple(TaskCase(**c) for c in projection["train"]),
            tuple(TaskCase(**c) for c in projection["validation"]), digest(encoded(projection)),
            pack_id, payload["name"], identity, target_id, payload["objective"]["policy_id"],
            tuple((c["id"], encoded(c.get("source", {})).decode("utf-8")) for p in ("train", "validation") for c in partition_cases(payload, p)), policy.execution_id, policy, loaded.file_hashes,
            tuple((policy.project(c).case_id, c["id"]) for p in ("train", "validation") for c in partition_cases(payload, p)),
            payload['objective']['direction'])

    def holdout(self, pack_id: str) -> tuple[TaskCase, ...]:
        payload = self._locate(pack_id)[2]
        policy = task_policy(payload["objective"]["policy_id"], policies=self.policies)
        return tuple(policy.project(c) for c in payload.get("holdout", []))

    def case_groups(self, pack_id: str) -> dict[str, str]:
        """Public grouping metadata without exposing acceptance fields."""
        payload = self._locate(pack_id)[2]
        policy = task_policy(payload['objective']['policy_id'], policies=self.policies)
        return {policy.project(c).case_id: c.get('group_id', '')
                for partition in ('train', 'validation', 'holdout') for c in partition_cases(payload, partition)}

    @contextmanager
    def _writer(self) -> Iterator[None]:
        safe_path(self.workspace, self.root).mkdir(parents=True, exist_ok=True)
        path = safe_path(self.workspace, self.root / ".write.lock")
        with path.open("a") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("another process is editing task packages") from exc
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _atomic_write(self, path: Path, data: bytes) -> None:
        path = safe_path(self.workspace, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".pack-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    def _write(self, path: Path, payload: PackageMaterial, *, original_hash: str | None = None) -> str:
        manifest, cases, holdout = package_documents(payload)
        validate_pack(manifest, cases=cases, holdout=holdout, policies=self.policies)
        path = safe_path(self.workspace, path)
        documents = {"pack.json": readable_json(manifest), manifest["files"]["cases"]: readable_json(cases)}
        if holdout is not None:
            documents[manifest["files"]["holdout"]] = readable_json(holdout)
        if original_hash is not None:
            # Unchanged files retain their exact bytes; budget the actual replacement.
            size = len(documents[manifest["files"]["cases"]]) + 1
            size += len(read_bytes(self.workspace, path))
            if holdout is not None:
                size += len(read_bytes(self.workspace, path.parent / manifest["files"]["holdout"]))
        else:
            size = sum(len(data) + 1 for data in documents.values())
        if size > 100_000:
            raise ValueError("task package exceeds 100 KB")
        if original_hash is not None:
            if self._read(path)[1] != original_hash:
                raise ValueError("task package changed; reload before saving")
            self._atomic_write(path.parent / manifest["files"]["cases"], documents[manifest["files"]["cases"]])
        else:
            if path.exists():
                raise ValueError("task package destination already exists")
            # Publish a complete new directory in one rename; readers never see partial data.
            path.parent.parent.mkdir(parents=True, exist_ok=True)
            temporary = Path(tempfile.mkdtemp(prefix=".new-", dir=path.parent.parent))
            try:
                for filename, data in documents.items():
                    (temporary / filename).write_bytes(data + b"\n")
                if path.parent.exists():
                    raise ValueError("task package destination already exists")
                os.rename(temporary, path.parent)
            finally:
                if temporary.exists():
                    for file in temporary.iterdir():
                        file.unlink()
                    temporary.rmdir()
        return payload["id"]

    def save_training(
        self, pack_id: str, input: str, expected: str, *, expected_hash: str = "",
        name: str = "", target_id: str = "base_prompt", reason: str = "",
        source: dict[str, str] | None = None, replace: bool = False, copy: bool = False,
        acceptance: dict[str, object] | None = None,
    ) -> str:
        """Explicitly save a human answer to train; never edit validation/holdout."""
        if acceptance is None:
            TaskCase(input, expected)
        elif not isinstance(input, str) or not input.strip() or len(input) > 4000:
            raise ValueError("invalid task input")
        with self._writer():
            if pack_id:
                path, writable, payload, identity = self._locate(pack_id)
                if not expected_hash or expected_hash != identity:
                    raise ValueError("task package changed; reload before saving")
                if target_id not in payload["compatible_targets"]:
                    raise ValueError("task package does not support the active target")
                if not writable:
                    if not copy:
                        raise ValueError("read-only task package; explicitly save a workspace copy")
                    payload["id"] = "task-" + uuid4().hex[:12]
                    payload["name"] = name or payload["name"] + " (copy)"
                    path = self.root / payload["id"] / "pack.json"
                    writable = False
            else:
                payload = self._new(name, target_id)
                path = self.root / payload["id"] / "pack.json"
                writable = False
            key = input_key(input)
            if any(input_key(c["input"]) == key for p in ("validation", "holdout") for c in partition_cases(payload, p)):
                raise ValueError("this input belongs to validation/holdout; change the partition explicitly first")
            found = next((c for c in payload["train"] if input_key(c["input"]) == key), None)
            policy = task_policy(payload["objective"]["policy_id"], policies=self.policies)
            if acceptance is None:
                if policy.required_fields - {"input", "expected"}:
                    raise ValueError("this policy needs declared entry_point/tests acceptance; edit cases.json or provide acceptance")
                acceptance = {"expected": expected}
            validate_acceptance(acceptance, policy)
            policy.project({"input": input, **acceptance})
            existing = {k: v for k, v in (found or {}).items() if k in policy.required_fields | policy.optional_fields and k != "input"}
            if found and existing == acceptance:
                return payload["id"] if writable else self._write(path, payload)
            if found and not replace:
                raise ValueError("conflicting training answer; explicitly replace or cancel")
            row = {k: v for k, v in (found or {}).items() if k not in policy.required_fields | policy.optional_fields}
            row.update(id=found["id"] if found else "case-" + uuid4().hex[:12], input=input, **acceptance)
            if reason:
                row["reason"] = reason
            if source:
                row["source"] = source
            if found:
                payload["train"][payload["train"].index(found)] = row
            else:
                payload["train"].append(row)
            return self._write(path, payload, original_hash=identity if writable else None)

    @staticmethod
    def _new(name: str, target_id: str) -> PackageMaterial:
        return {"description": "Human-corrected regression tasks", "files": {"cases": "cases.json"}, "id": "task-" + uuid4().hex[:12], "name": name,
            "task_schema": "single-turn-text-v1", "target_schema": "text-v1", "compatible_targets": [target_id],
            "objective": {"policy_id": "normalized-exact-v1", "direction": "max"}, "train": [], "validation": []}


