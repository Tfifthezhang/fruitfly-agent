"""Public offline package checks and answer scoring.

Run from a workspace root; never constructs a Provider or activates a target.
"""
from __future__ import annotations

import argparse
import asyncio
from inspect import isawaitable
import json
from pathlib import Path

from fruitfly_agent.lab.improvement.assessment.scorers.policies import ScoreResult, task_policy
from .packages import load_pack, read_bytes, unique_keys


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
    parser = argparse.ArgumentParser(description="Offline task package validation and scoring; no model requests.")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "self-check", "score"):
        sub = commands.add_parser(command)
        sub.add_argument("pack", type=Path)
        if command == "self-check":
            sub.add_argument("--references", type=Path, help="defaults to references.json beside pack")
        if command == "score":
            sub.add_argument("--case", required=True)
            sub.add_argument("--answer-file", required=True, type=Path)
    args = parser.parse_args(argv)
    workspace = Path.cwd()
    try:
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
        refs = json.loads(read_bytes(workspace, path).decode("utf-8"), object_pairs_hook=unique_keys)
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
