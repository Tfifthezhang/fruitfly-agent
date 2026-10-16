"""Export official task material and complete owned receipts to a neutral format."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tomllib
from typing import Any

from fruitfly_agent.lab.improvement.experiments import TaskReference, TaskRunEvidence, EvidenceArtifact
from fruitfly_agent.lab.improvement.contracts.versions import canonical_json, content_hash, SystemVersion


def material_hash(directory: Path) -> str:
    rows = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("task material snapshot cannot contain symlinks")
        if path.is_file():
            rows.append((path.relative_to(directory).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    return content_hash(canonical_json(rows))


def resolve_task_material(raw: dict) -> Path:
    from harbor.models.trial.config import TaskConfig  # type: ignore[import-not-found]
    config = raw.get("config", {}).get("task")
    if not isinstance(config, dict):
        raise ValueError("Harbor trial has no resolved task configuration")
    return TaskConfig.model_validate(config).get_local_path()


def export_harbor_evidence(job_directory: Path, *, dataset: str, output_directory: Path,
                           material_resolver=resolve_task_material) -> dict:
    output_directory.mkdir(parents=True, exist_ok=True)
    runs, errors, materials = [], [], {}
    for index, result_path in enumerate(sorted(job_directory.glob("*/result.json"))):
        raw = json.loads(result_path.read_text(encoding="utf-8"))
        trial = result_path.parent
        try:
            source = Path(material_resolver(raw)).resolve()
            digest = material_hash(source)
            config = tomllib.loads((source / "task.toml").read_text(encoding="utf-8"))
            if config.get("steps") or (source / "steps").exists():
                raise ValueError("multi-step task evidence is not supported by this exporter")
            instruction = (source / "instruction.md").read_text(encoding="utf-8")
            task_config = raw.get("config", {}).get("task", {})
            revision = task_config.get("git_commit_id") or raw.get("task_id", {}).get("git_commit_id") or "local:" + digest
            task = TaskReference(dataset, raw["task_name"], revision, digest, instruction,
                "harbor-official:" + content_hash((source / "tests/test.sh").read_text(encoding="utf-8")),
                canonical_json(config.get("environment", {})))
            material_path = output_directory / "tasks" / digest.removeprefix("sha256:") / task.task_id.split("/")[-1]
            if not material_path.exists():
                material_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, material_path)
            if material_hash(material_path) != digest:
                raise ValueError("copied task material changed")
            materials[task.reference_id] = material_path.relative_to(output_directory).as_posix()
            owned = output_directory / "runs" / f"{index:06d}"
            owned.mkdir(parents=True, exist_ok=True)
            artifacts = []
            for relative, kind in (("agent/session.jsonl", "trajectory"), ("result.json", "official-result"),
                                   ("agent/trial-receipt.json", "runtime-receipt")):
                path = trial / relative
                if path.is_file() and not path.is_symlink():
                    target = owned / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
                    artifacts.append(EvidenceArtifact(kind, target.relative_to(output_directory).as_posix(),
                                                     "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()))
            for path in sorted((trial / "verifier").glob("*")):
                if path.is_file() and not path.is_symlink():
                    target = owned / "verifier" / path.name
                    target.parent.mkdir(exist_ok=True)
                    shutil.copyfile(path, target)
                    artifacts.append(EvidenceArtifact("verifier-log", target.relative_to(output_directory).as_posix(),
                                                     "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()))
            rewards = (raw.get("verifier_result") or {}).get("rewards") or {}
            reward = rewards.get("reward")
            if reward is None and len(rewards) == 1:
                reward = next(iter(rewards.values()))
            exception = raw.get("exception_info")
            admissible = isinstance(reward, (int, float)) and not isinstance(reward, bool)
            status: Any = "error" if exception else "scored" if admissible else "unscored"
            receipt_path = trial / "agent/trial-receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else {}
            if receipt and receipt.get("status") != "completed":
                status = receipt.get("status") if receipt.get("status") in {"cancelled", "budget_exhausted"} else "error"
            session = trial / "agent/session.jsonl"
            output = receipt.get("output", "")
            if not output and session.is_file():
                answers: list[str] = []
                for line in session.read_text(encoding="utf-8").splitlines():
                    row = json.loads(line)
                    message = row.get("message", {})
                    if row.get("type") == "message" and message.get("role") == "assistant":
                        answers.extend(c.get("text", "") for c in message.get("content", ()) if c.get("type") == "text")
                output = "\n".join(answers)
            runtime = receipt.get("runtime") or (raw.get("agent_result") or {}).get("metadata", {}).get("runtime_manifest") or {}
            evidence = TaskRunEvidence(str(raw.get("id") or trial.name), task, status,
                float(reward) if status == "scored" and isinstance(reward, (int, float)) else None, output,
                "Official reward: " + str(reward) if not exception else str(exception.get("exception_type", "RunnerError")),
                tuple(artifacts), SystemVersion.from_dict(receipt["version"]) if receipt.get("version") else None,
                receipt.get("conditions_id", ""), receipt.get("model_calls"), runtime.get("digest", ""),
                content_hash(canonical_json(receipt["execution_environment"])) if receipt.get("execution_environment") else "")
            runs.append(evidence.to_dict())
        except (OSError, ValueError, TypeError, KeyError, ImportError) as exc:
            errors.append({"trial": trial.name, "error": type(exc).__name__, "reason": str(exc)[:300]})
    payload = {"schema_version": 1, "dataset": dataset, "runs": runs, "materials": materials, "errors": errors}
    (output_directory / "evidence.json").write_text(canonical_json(payload), encoding="utf-8")
    return payload
