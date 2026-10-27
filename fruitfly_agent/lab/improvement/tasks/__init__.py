"""Bounded task packages, authorized training edits and immutable search material."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from uuid import uuid4
from typing import Iterator, NotRequired, Protocol, Sequence, TypedDict, cast

from fruitfly_agent.lab.improvement.tasks.models import TaskCase
from fruitfly_agent.lab.improvement.tasks.scoring import TaskPolicy, builtin_task_policies, task_policy

TASK_PACK_COMPONENT = "improvement-task-packs"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class _Objective(TypedDict):
    policy_id: str
    direction: str


class _TaskMaterial(TypedDict):
    """Validated metadata and policy-defined case mappings, never a raw JSON input."""
    id: str
    name: str
    description: str
    task_schema: str
    target_schema: str
    compatible_targets: list[str]
    objective: _Objective
    files: dict[str, str]
    default_direction: NotRequired[str]
    train: list[dict]
    validation: list[dict]
    holdout: NotRequired[list[dict]]


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def readable_json(value: object) -> bytes:
    """Readable package JSON: expand structure, keep deeply nested values together.

    This controls presentation only; content-addressed receipts still use encoded().
    """
    def render(item: object, depth: int = 0) -> str:
        compact = json.dumps(item, ensure_ascii=False, allow_nan=False)
        if not isinstance(item, (dict, list)) or not item:
            return compact
        children = item.values() if isinstance(item, dict) else item
        if depth >= 5 or (depth >= 3 and all(not isinstance(v, (dict, list)) for v in children) and len(compact) <= 120):
            return compact
        indent = "  " * (depth + 1)
        if isinstance(item, dict):
            parts = [indent + json.dumps(k, ensure_ascii=False) + ": " + render(v, depth + 1) for k, v in item.items()]
            return "{\n" + ",\n".join(parts) + "\n" + "  " * depth + "}"
        return "[\n" + ",\n".join(indent + render(v, depth + 1) for v in item) + "\n" + "  " * depth + "]"
    return render(value).encode("utf-8")


def input_key(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip()


def safe_path(workspace: Path, path: Path) -> Path:
    """Reject escaping paths and symlinks, including directory symlinks."""
    root = workspace.resolve()
    candidate = path if path.is_absolute() else root / path
    try:
        relative = candidate.relative_to(root)
        candidate.resolve().relative_to(root)
    except ValueError as exc:
        raise ValueError("task package path must stay inside the workspace") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("task package paths must not contain symlinks")
    return candidate


def read_bytes(workspace: Path, path: Path) -> bytes:
    source = safe_path(workspace, path)
    with source.open("rb") as stream:
        data = stream.read(100_001)
    if len(data) > 100_000:
        raise ValueError("task package exceeds 100 KB")
    return data


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _validate_manifest_fields(payload: object) -> dict:
    required = {"id", "name", "description", "task_schema", "target_schema", "compatible_targets", "objective", "files"}
    if not isinstance(payload, dict) or not required <= payload.keys() or payload.keys() - required - {"default_direction"}:
        raise ValueError("invalid task package fields")
    if not isinstance(payload["id"], str) or not _ID.fullmatch(payload["id"]):
        raise ValueError("invalid task package id")
    for key, limit in (("name", 120), ("description", 500), ("default_direction", 500)):
        value = payload.get(key, "")
        if not isinstance(value, str) or len(value) > limit or key in {"name", "description"} and not value.strip():
            raise ValueError(f"invalid task package {key}")
    return payload


def _validate_documents(files: object, cases: object, holdout: object) -> dict:
    if not isinstance(files, dict) or "cases" not in files or files.keys() - {"cases", "holdout"}:
        raise ValueError("files must declare cases and optional holdout")
    for filename in files.values():
        if not isinstance(filename, str) or not filename or Path(filename).name != filename or filename in {".", "..", "pack.json", "references.json", "baseline.txt"} or not filename.endswith(".json"):
            raise ValueError("task file must be a local JSON filename")
    if len(set(files.values())) != len(files):
        raise ValueError("task file references must be distinct")
    if not isinstance(cases, dict) or set(cases) != {"train", "validation"}:
        raise ValueError("cases.json must contain only train and validation")
    if "holdout" in files:
        if not isinstance(holdout, dict) or set(holdout) != {"holdout"}:
            raise ValueError("declared holdout.json must contain only holdout")
    elif holdout is not None:
        raise ValueError("holdout data must be declared in files")
    return cases


def _validate_policy(payload: dict, policies: Sequence[TaskPolicy] | None) -> TaskPolicy:
    objective = payload["objective"]
    if not isinstance(objective, dict) or set(objective) != {"policy_id", "direction"} or objective["direction"] != "max":
        raise ValueError("unsupported objective policy")
    policy = task_policy(objective["policy_id"], policies=policies)
    if payload["task_schema"] != policy.task_schema or payload["target_schema"] != "text-v1":
        raise ValueError("unsupported task or target schema for this policy")
    targets = payload["compatible_targets"]
    if not isinstance(targets, list) or not targets or len(targets) > 16 or any(not isinstance(t, str) or not t.strip() for t in targets) or len(set(targets)) != len(targets):
        raise ValueError("invalid compatible_targets")
    return policy


def _validate_acceptance(acceptance: object, policy: TaskPolicy) -> dict:
    if not isinstance(acceptance, dict):
        raise ValueError("invalid acceptance for " + policy.task_schema)
    required = policy.required_fields - {"input"}
    allowed = policy.required_fields | policy.optional_fields
    if not required <= acceptance.keys() or acceptance.keys() - allowed or "input" in acceptance:
        raise ValueError("invalid acceptance for " + policy.task_schema)
    return acceptance


def _project_envelope(envelope: object, policy: TaskPolicy) -> dict:
    metadata = {"id", "tags", "group_id", "reason", "source"}
    if not isinstance(envelope, dict):
        raise ValueError("invalid task case envelope")
    if not {"id", "input", "acceptance"} <= envelope.keys() or envelope.keys() - metadata - {"input", "acceptance"}:
        raise ValueError("invalid task case envelope")
    acceptance = _validate_acceptance(envelope["acceptance"], policy)
    row = {k: v for k, v in envelope.items() if k != "acceptance"}
    row.update(acceptance)
    return row


def _validate_case_metadata(row: dict) -> None:
    if not isinstance(row.get("reason", ""), str) or len(row.get("reason", "")) > 1000:
        raise ValueError("reason exceeds 1000 characters")
    tags = row.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 20 or any(not isinstance(t, str) or len(t) > 120 for t in tags):
        raise ValueError("invalid tags")
    source = row.get("source", {})
    if not isinstance(source, dict) or len(source) > 8 or any(not isinstance(k, str) or not isinstance(v, str) or len(k) > 80 or len(v) > 1000 for k, v in source.items()):
        raise ValueError("invalid source metadata")


def validate_pack(
    payload: object, *, cases: object = None, holdout: object = None,
    policies: Sequence[TaskPolicy] | None = None,
) -> _TaskMaterial:
    """Validate raw v2 documents in order; return policy-projected service material."""
    manifest = _validate_manifest_fields(payload)
    documents = _validate_documents(manifest["files"], cases, holdout)
    policy = _validate_policy(manifest, policies)
    return _validate_partitions(manifest, documents, holdout, policy)


def _validate_partitions(payload: dict, cases: dict, holdout: object, policy: TaskPolicy) -> _TaskMaterial:
    material = dict(payload)
    ids: set[str] = set()
    inputs: dict[str, str] = {}
    groups: dict[str, str] = {}
    for partition in ("train", "validation", "holdout"):
        rows = holdout.get(partition, []) if partition == "holdout" and isinstance(holdout, dict) else (
            [] if partition == "holdout" else cases[partition]
        )
        if not isinstance(rows, list) or len(rows) > 12:
            raise ValueError(f"{partition} must contain at most 12 cases")
        projected = []
        for envelope in rows:
            row = _project_envelope(envelope, policy)
            projected.append(row)
            if not isinstance(row["id"], str) or not _ID.fullmatch(row["id"]) or row["id"] in ids:
                raise ValueError("invalid or duplicate case id")
            ids.add(row["id"])
            policy.project(row)
            key = input_key(row["input"])
            if key in inputs:
                raise ValueError("duplicate input or conflicting answers across task partitions")
            inputs[key] = partition
            group = row.get("group_id", "")
            if not isinstance(group, str) or len(group) > 120:
                raise ValueError("invalid group_id")
            if group and group in groups and groups[group] != partition:
                raise ValueError("group_id overlaps task partitions")
            if group:
                groups[group] = partition
            _validate_case_metadata(row)
        material[partition] = projected
    if len(encoded(payload)) + len(encoded(cases)) + 2 + (len(encoded(holdout)) + 1 if holdout is not None else 0) > 100_000:
        raise ValueError("task package exceeds 100 KB")
    # Only the completed validation path may label raw mappings as service material.
    return cast(_TaskMaterial, material)


def package_documents(material: _TaskMaterial) -> tuple[dict, dict, dict | None]:
    """Serialize projected task material into the single canonical v2 layout."""
    manifest: dict = {k: v for k, v in material.items() if k not in {"train", "validation", "holdout"}}
    def envelopes(partition: str) -> list[dict]:
        result = []
        for row in _partition(material, partition):
            base = {k: v for k, v in row.items() if k in {"id", "input", "tags", "group_id", "reason", "source"}}
            base["acceptance"] = {k: v for k, v in row.items() if k not in base}
            result.append(base)
        return result
    cases = {p: envelopes(p) for p in ("train", "validation")}
    holdout = {"holdout": envelopes("holdout")} if "holdout" in manifest["files"] else None
    return manifest, cases, holdout


def _partition(material: _TaskMaterial, name: str) -> list[dict]:
    if name == "train":
        return material.get("train", [])
    if name == "validation":
        return material.get("validation", [])
    return material.get("holdout", [])


@dataclass(frozen=True)
class LoadedTaskPack:
    material: _TaskMaterial
    source_hash: str
    file_hashes: tuple[tuple[str, str], ...]


def load_pack(workspace: Path, path: Path, *, policies: Sequence[TaskPolicy] | None = None) -> LoadedTaskPack:
    """Read a consistent, bounded task package. No model or code execution."""
    workspace, path = Path(workspace).resolve(), Path(path)
    manifest_bytes = read_bytes(workspace, path)
    manifest = json.loads(manifest_bytes.decode("utf-8"), object_pairs_hook=_unique_keys)
    # Validate references before opening any declared file.
    _validate_manifest_fields(manifest)
    files = manifest.get("files")
    if not isinstance(files, dict) or "cases" not in files or files.keys() - {"cases", "holdout"}:
        raise ValueError("invalid task file references")
    documents, contents = {}, [(path, manifest_bytes)]
    for key, filename in files.items():
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".json") or filename in {"pack.json", "references.json"}:
            raise ValueError("task file must be a local JSON filename")
        file = path.parent / filename
        data = read_bytes(workspace, file)
        contents.append((file, data))
        documents[key] = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_keys)
    if sum(len(data) for _, data in contents) > 100_000:
        raise ValueError("task package exceeds 100 KB")
    material = validate_pack(manifest, cases=documents["cases"], holdout=documents.get("holdout"), policies=policies)
    # Re-read every file; concurrent edits must never produce a mixed job.
    for file, data in contents:
        if read_bytes(workspace, file) != data:
            raise ValueError("task package changed while reading; reload")
    hashes = tuple(sorted((file.name, digest(data)) for file, data in contents))
    return LoadedTaskPack(material, digest(encoded(hashes)), hashes)


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


class TaskSource(Protocol):
    """Projects authorized material to immutable single-turn cases."""
    def freeze(self, pack_id: str, target_id: str) -> FrozenTaskSuite: ...


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

    def _read(self, path: Path) -> tuple[_TaskMaterial, str]:
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

    def _locate(self, pack_id: str) -> tuple[Path, bool, _TaskMaterial, str]:
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
        projection = {p: [policy.project(c).__dict__ for c in _partition(payload, p)] for p in ("train", "validation")}
        return FrozenTaskSuite(tuple(TaskCase(**c) for c in projection["train"]),
            tuple(TaskCase(**c) for c in projection["validation"]), digest(encoded(projection)),
            pack_id, payload["name"], identity, target_id, payload["objective"]["policy_id"],
            tuple((c["id"], encoded(c.get("source", {})).decode("utf-8")) for p in ("train", "validation") for c in _partition(payload, p)), policy.execution_id, policy, loaded.file_hashes,
            tuple((policy.project(c).case_id, c["id"]) for p in ("train", "validation") for c in _partition(payload, p)),
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
                for partition in ('train', 'validation', 'holdout') for c in _partition(payload, partition)}

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

    def _write(self, path: Path, payload: _TaskMaterial, *, original_hash: str | None = None) -> str:
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
            if any(input_key(c["input"]) == key for p in ("validation", "holdout") for c in _partition(payload, p)):
                raise ValueError("this input belongs to validation/holdout; change the partition explicitly first")
            found = next((c for c in payload["train"] if input_key(c["input"]) == key), None)
            policy = task_policy(payload["objective"]["policy_id"], policies=self.policies)
            if acceptance is None:
                if policy.required_fields - {"input", "expected"}:
                    raise ValueError("this policy needs declared entry_point/tests acceptance; edit cases.json or provide acceptance")
                acceptance = {"expected": expected}
            _validate_acceptance(acceptance, policy)
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
    def _new(name: str, target_id: str) -> _TaskMaterial:
        return {"description": "Human-corrected regression tasks", "files": {"cases": "cases.json"}, "id": "task-" + uuid4().hex[:12], "name": name,
            "task_schema": "single-turn-text-v1", "target_schema": "text-v1", "compatible_targets": [target_id],
            "objective": {"policy_id": "normalized-exact-v1", "direction": "max"}, "train": [], "validation": []}


class TaskSnapshotStore:
    """Atomic content-addressed search receipts; rejects relocation and corruption."""
    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace).resolve()
        self.root = self.workspace / ".fruitfly/improvement/task-snapshots"

    def freeze(self, payload: object) -> tuple[Path, str]:
        data = encoded(payload)
        identity = digest(data)
        path = safe_path(self.workspace, self.root / (identity[7:] + ".json"))
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".snapshot-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
            self.verify(path, identity)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return path, identity

    def verify(self, path: Path, identity: str) -> None:
        source = safe_path(self.workspace, path)
        if digest(source.read_bytes()) != identity:
            raise ValueError("improvement snapshot corrupted")
