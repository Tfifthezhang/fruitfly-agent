"""Public offline package checks, answer scoring and explicit v1 migration.

Run from a workspace root; never constructs a Provider or activates a target.
"""
from __future__ import annotations

import argparse
import asyncio
from inspect import isawaitable
import json
from pathlib import Path

from .scoring import ScoreResult, task_policy
from .task_packs import (TaskPackCatalog, encoded, load_pack, package_documents,
                         read_bytes, safe_path, validate_pack, _unique_keys)


def migrate_material(payload):
    """Convert a declared v1 package; return v2 material and optional references."""
    required = {"schema_version", "id", "name", "task_schema", "target_schema", "compatible_targets", "objective", "train", "validation"}
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload.get("schema_version") != 1 or not required <= payload.keys() or payload.keys() - required - {"description", "holdout"}:
        raise ValueError("migration requires a schema 1 package, not legacy cases JSON")
    material = dict(payload)
    material.update(schema_version=2, description=payload.get("description") or payload["name"], files={"cases": "cases.json"})
    if "holdout" in payload:
        material["files"]["holdout"] = "holdout.json"
    policy = task_policy(payload["objective"]["policy_id"])
    references = {}
    for partition in ("train", "validation", "holdout"):
        rows = []
        for old in payload.get(partition, []):
            row = dict(old)
            # A v1 Python expected was an optional human reference, never a test.
            if "expected" not in policy.required_fields | policy.optional_fields and "expected" in row:
                references[row["id"]] = row.pop("expected")
            rows.append(row)
        material[partition] = rows
    manifest, cases, holdout = package_documents(material)
    return validate_pack(manifest, cases=cases, holdout=holdout), references


def migrate_pack(workspace, source, destination):
    """Publish a new v2 directory without changing the old package or evidence."""
    workspace = Path(workspace).resolve()
    payload = json.loads(read_bytes(workspace, Path(source)).decode("utf-8"), object_pairs_hook=_unique_keys)
    material, references = migrate_material(payload)
    destination = safe_path(workspace, Path(destination))
    catalog = TaskPackCatalog(workspace)
    with catalog._writer():
        catalog._write(destination / "pack.json", material)
        if references:
            catalog._atomic_write(destination / "references.json", encoded(references))
    return load_pack(workspace, destination / "pack.json")


async def score_answer(workspace, pack_path, case_id, output):
    """Score a saved answer with the same registered policy used in searches."""
    pack = load_pack(workspace, pack_path).material
    row = next((c for part in ("train", "validation", "holdout") for c in pack[part] if c["id"] == case_id), None)
    if row is None:
        raise ValueError("unknown case id")
    policy = task_policy(pack["objective"]["policy_id"])
    policy.check_available()
    result = policy.score(output, policy.project(row))
    if isawaitable(result):
        result = await result
    return result if isinstance(result, ScoreResult) else ScoreResult(result)


async def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline task package validation/scoring/migration; no model requests.")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "self-check", "score", "migrate"):
        sub = commands.add_parser(command)
        sub.add_argument("pack", type=Path)
        if command == "self-check":
            sub.add_argument("--references", type=Path, help="defaults to references.json beside pack")
        if command == "score":
            sub.add_argument("--case", required=True)
            sub.add_argument("--answer-file", required=True, type=Path)
        if command == "migrate":
            sub.add_argument("--to", required=True, type=Path, help="new, nonexistent package directory")
    args = parser.parse_args(argv)
    workspace = Path.cwd()
    try:
        if args.command == "migrate":
            pack = migrate_pack(workspace, args.pack, args.to)
            print(f"Migrated {pack.material['id']}; source unchanged; {pack.source_hash}")
            return 0
        loaded = load_pack(workspace, args.pack)
        pack = loaded.material
        if args.command == "check":
            counts = ", ".join(f"{p}={len(pack[p])}" for p in ("train", "validation", "holdout"))
            print(f"{pack['id']}: {counts}; {pack['objective']['policy_id']}; {loaded.source_hash}")
            if not pack["train"] or not pack["validation"]:
                print("Valid storage; not ready to search: train and validation are required.")
            return 0
        if args.command == "score":
            path = args.answer_file
            with path.open("rb") as stream:
                answer = stream.read(30001)
            if len(answer) > 30000:
                raise ValueError("answer file exceeds 30 KB")
            result = await score_answer(workspace, args.pack, args.case, answer.decode("utf-8"))
            print(f"{args.case}: {result.score:.3f} · {result.feedback}")
            return 0 if result.score == 1 else 1
        path = args.references or args.pack.parent / "references.json"
        refs = json.loads(read_bytes(workspace, path).decode("utf-8"), object_pairs_hook=_unique_keys)
        if not isinstance(refs, dict) or any(not isinstance(v, str) for v in refs.values()):
            raise ValueError("references must map case IDs to answer text")
        policy = task_policy(pack["objective"]["policy_id"])
        policy.check_available()
        rows = [c for part in ("train", "validation", "holdout") for c in pack[part]]
        if set(refs) != {c["id"] for c in rows}:
            raise ValueError("references must cover exactly the declared cases")
        success = True
        for row in rows:
            result = policy.score(refs[row["id"]], policy.project(row))
            if isawaitable(result):
                result = await result
            if not isinstance(result, ScoreResult):
                result = ScoreResult(result)
            print(f"{row['id']}: {result.score:.3f} · {result.feedback}")
            success = success and result.score == 1
        return 0 if success else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"Task package error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
