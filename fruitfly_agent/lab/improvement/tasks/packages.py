"""Canonical task-package validation, serialization and bounded loading."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from typing import NotRequired, Sequence, TypedDict, cast
from fruitfly_agent.lab.improvement.assessment.scorers.policies import TaskPolicy, task_policy

TASK_PACK_COMPONENT = "improvement-task-packs"


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class _Objective(TypedDict):
    policy_id: str
    direction: str


class PackageMaterial(TypedDict):
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


def unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
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


def validate_acceptance(acceptance: object, policy: TaskPolicy) -> dict:
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
    acceptance = validate_acceptance(envelope["acceptance"], policy)
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
) -> PackageMaterial:
    """Validate raw v2 documents in order; return policy-projected service material."""
    manifest = _validate_manifest_fields(payload)
    documents = _validate_documents(manifest["files"], cases, holdout)
    policy = _validate_policy(manifest, policies)
    return _validate_partitions(manifest, documents, holdout, policy)


def _validate_partitions(payload: dict, cases: dict, holdout: object, policy: TaskPolicy) -> PackageMaterial:
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
    return cast(PackageMaterial, material)


def package_documents(material: PackageMaterial) -> tuple[dict, dict, dict | None]:
    """Serialize projected task material into the single canonical v2 layout."""
    manifest: dict = {k: v for k, v in material.items() if k not in {"train", "validation", "holdout"}}
    def envelopes(partition: str) -> list[dict]:
        result = []
        for row in partition_cases(material, partition):
            base = {k: v for k, v in row.items() if k in {"id", "input", "tags", "group_id", "reason", "source"}}
            base["acceptance"] = {k: v for k, v in row.items() if k not in base}
            result.append(base)
        return result
    cases = {p: envelopes(p) for p in ("train", "validation")}
    holdout = {"holdout": envelopes("holdout")} if "holdout" in manifest["files"] else None
    return manifest, cases, holdout


def partition_cases(material: PackageMaterial, name: str) -> list[dict]:
    if name == "train":
        return material.get("train", [])
    if name == "validation":
        return material.get("validation", [])
    return material.get("holdout", [])


@dataclass(frozen=True)
class LoadedTaskPack:
    material: PackageMaterial
    source_hash: str
    file_hashes: tuple[tuple[str, str], ...]


def load_pack(workspace: Path, path: Path, *, policies: Sequence[TaskPolicy] | None = None) -> LoadedTaskPack:
    """Read a consistent, bounded task package. No model or code execution."""
    workspace, path = Path(workspace).resolve(), Path(path)
    manifest_bytes = read_bytes(workspace, path)
    manifest = json.loads(manifest_bytes.decode("utf-8"), object_pairs_hook=unique_keys)
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
        documents[key] = json.loads(data.decode("utf-8"), object_pairs_hook=unique_keys)
    if sum(len(data) for _, data in contents) > 100_000:
        raise ValueError("task package exceeds 100 KB")
    material = validate_pack(manifest, cases=documents["cases"], holdout=documents.get("holdout"), policies=policies)
    # Re-read every file; concurrent edits must never produce a mixed job.
    for file, data in contents:
        if read_bytes(workspace, file) != data:
            raise ValueError("task package changed while reading; reload")
    hashes = tuple(sorted((file.name, digest(data)) for file, data in contents))
    return LoadedTaskPack(material, digest(encoded(hashes)), hashes)


