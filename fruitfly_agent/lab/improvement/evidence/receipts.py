"""Benchmark-neutral task references, receipts and fixed experiment partitions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from fruitfly_agent.lab.improvement.contracts.versions import SystemVersion, canonical_json, content_hash, require_hash


@dataclass(frozen=True)
class TaskReference:
    dataset: str
    task_id: str
    source_revision: str
    material_hash: str
    instruction: str
    verifier_id: str
    environment_id: str

    def __post_init__(self) -> None:
        for value in (self.dataset, self.task_id, self.source_revision, self.verifier_id, self.environment_id):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("task references need dataset, source, verifier and environment identities")
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]*", self.task_id)
                or ".." in self.task_id or not isinstance(self.instruction, str)
                or not self.instruction.strip() or len(self.instruction) > 120000):
            raise ValueError("task needs an exact registry name and bounded complete instruction")
        require_hash(self.material_hash)

    @property
    def reference_id(self) -> str:
        return content_hash(canonical_json(self.to_dict()))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> TaskReference:
        if not isinstance(data, dict) or set(data) != set(cls.__dataclass_fields__):
            raise ValueError("invalid task reference")
        return cls(**data)


@dataclass(frozen=True)
class EvidenceArtifact:
    kind: str
    path: str
    digest: str

    def __post_init__(self) -> None:
        if (not isinstance(self.kind, str) or not self.kind.strip()
                or not isinstance(self.path, str) or self.path.startswith("/")
                or "\\" in self.path or any(p in {"", ".", ".."} for p in self.path.split("/"))):
            raise ValueError("evidence paths must remain relative to their owned result directory")
        require_hash(self.digest)


@dataclass(frozen=True)
class TaskRunEvidence:
    run_id: str
    task: TaskReference
    status: str
    score: float | None
    output: str = ""
    feedback: str = ""
    artifacts: tuple[EvidenceArtifact, ...] = ()
    version: SystemVersion | None = None
    conditions_id: str = ""
    model_calls: int | None = None
    runtime_digest: str = ""
    environment_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        if not isinstance(self.run_id, str) or not self.run_id.strip() or not isinstance(self.task, TaskReference):
            raise ValueError("run evidence needs an actual task and run identity")
        if self.status not in {"scored", "error", "cancelled", "unscored", "budget_exhausted"}:
            raise ValueError("invalid task run status")
        if self.status == "scored":
            if isinstance(self.score, bool) or not isinstance(self.score, (int, float)) or not math.isfinite(self.score):
                raise ValueError("scored tasks need a finite official reward")
        elif self.score is not None:
            raise ValueError("unscored or infrastructure failures must not invent a reward")
        if any(not isinstance(v, str) for v in (self.output, self.feedback)):
            raise ValueError("run output and feedback must be text")
        if self.model_calls is not None and (type(self.model_calls) is not int or self.model_calls < 0):
            raise ValueError("model call usage must be known nonnegative integer or unknown")
        if self.conditions_id:
            require_hash(self.conditions_id)
        if self.version is not None and not isinstance(self.version, SystemVersion):
            raise ValueError("run evidence must bind a complete H/I/S version")

    def to_dict(self) -> dict:
        value = asdict(self)
        value["task"] = self.task.to_dict()
        value["version"] = self.version.to_dict() if self.version else None
        return value

    @classmethod
    def from_dict(cls, data: dict) -> TaskRunEvidence:
        if not isinstance(data, dict) or set(data) != set(cls.__dataclass_fields__):
            raise ValueError("invalid task run evidence")
        return cls(**{**data, "task": TaskReference.from_dict(data["task"]),
                      "artifacts": tuple(EvidenceArtifact(**a) for a in data["artifacts"]),
                      "version": SystemVersion.from_dict(data["version"]) if data["version"] else None})
