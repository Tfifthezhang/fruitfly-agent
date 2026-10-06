"""Run-owned durable human-review inbox for text optimizer proposals."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import json
import hashlib
import os
from pathlib import Path
import re
import tempfile
import uuid
from typing import Any, Mapping


from .artifacts import DataArtifactStore
from fruitfly_agent.lab.optimization.text_optimizer import SearchReport


_CANDIDATE_ID = re.compile(r"^[0-9a-f]{32}$")
_STATUSES = frozenset({
    "proposed", "reviewed", "deferred", "rejected",
    "selected_for_next_session", "adopted", "stale",
})


@dataclass(frozen=True)
class CandidateRecord:
    candidate_id: str
    algorithm: str
    target: str
    parent_manifest_digest: str
    parent_target_reference: str
    parent_target_hash: str
    artifact_id: str
    cases_digest: str
    direction: str
    seed_score: float | None
    validation_score: float | None
    metric_calls: int
    created_at: str
    status: str = "proposed"
    notified: bool = False
    evidence: tuple[tuple[str, str], ...] = ()
    binding_kind: str = "prompt"
    binding_key: str = ""
    activated_manifest_digest: str = ""
    config_path: str = ""
    profile_id: str = ""
    report: dict | None = None
    task_pack_id: str = ""
    task_pack_name: str = ""
    task_pack_hash: str = ""

    def __post_init__(self) -> None:
        if any(not isinstance(v, str) for v in (self.task_pack_id, self.task_pack_name, self.task_pack_hash)):
            raise ValueError('candidate task attribution must be text')
        if not _CANDIDATE_ID.fullmatch(self.candidate_id):
            raise ValueError("invalid Optimization candidate id")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", self.algorithm) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", self.target):
            raise ValueError("unsupported optimization candidate")
        if self.binding_kind not in {"prompt", "artifact"} or (self.binding_kind == "artifact" and not self.binding_key):
            raise ValueError("invalid candidate binding")
        if not isinstance(self.metric_calls, int) or isinstance(self.metric_calls, bool) or self.metric_calls < 0:
            raise ValueError("invalid candidate metric call count")
        if any(not isinstance(pair, (list, tuple)) or len(pair) != 2 or not all(isinstance(v, str) for v in pair) for pair in self.evidence):
            raise ValueError("candidate evidence must contain text label/value pairs")
        object.__setattr__(self, "evidence", tuple(tuple(pair) for pair in self.evidence))
        if self.status not in _STATUSES:
            raise ValueError("invalid Optimization candidate status")
        if not isinstance(self.config_path, str) or not isinstance(self.profile_id, str) or bool(self.config_path) != bool(self.profile_id):
            raise ValueError('candidate configuration/profile scope must be paired text')
        if self.report is not None:
            object.__setattr__(self, 'report', asdict(SearchReport(**self.report)))


class CandidateStore:
    """Small JSON inbox; artifacts remain immutable in DataArtifactStore."""

    def __init__(self, root: Path, artifacts: DataArtifactStore) -> None:
        self.root = root.resolve()
        self.artifacts = artifacts

    def create(
        self,
        *,
        text: str,
        algorithm: str,
        parent_manifest: Mapping[str, Any],
        cases_digest: str,
        direction: str,
        seed_score: float,
        validation_score: float,
        metric_calls: int,
        evidence: tuple[tuple[str, str], ...] = (),
        snapshot,
        config_path: str = "",
        profile_id: str = "",
        report=None,
        task_pack_id="", task_pack_name="", task_pack_hash="",
    ) -> CandidateRecord:
        validate_candidate_text(text)
        parent_artifact = self.artifacts.put_text(snapshot.text)
        artifact = self.artifacts.put_text(text)
        record = CandidateRecord(
            candidate_id=uuid.uuid4().hex,
            algorithm=algorithm,
            target=snapshot.target_id,
            parent_manifest_digest=str(parent_manifest["digest"]),
            parent_target_reference=parent_artifact.artifact_id,
            parent_target_hash=snapshot.content_hash,
            artifact_id=artifact.artifact_id,
            cases_digest=cases_digest,
            direction=direction,
            seed_score=seed_score,
            validation_score=validation_score,
            metric_calls=metric_calls,
            evidence=evidence,
            binding_kind=snapshot.binding.kind, binding_key=snapshot.binding.key,
            created_at=datetime.now(UTC).isoformat(),
            config_path=config_path, profile_id=profile_id,
            report=asdict(report) if report is not None else None,
            task_pack_id=task_pack_id, task_pack_name=task_pack_name, task_pack_hash=task_pack_hash,
        )
        self._write(record, create=True)
        return record

    def read(self, candidate_id: str) -> CandidateRecord:
        path = self._path(candidate_id)
        if path.is_symlink():
            raise ValueError("candidate record must not be a symlink")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"unknown candidate {candidate_id}") from exc
        # Read existing prompt inbox records through an explicit data migration.
        if "parent_prompt_reference" in data:
            data["parent_target_reference"] = data.pop("parent_prompt_reference")
            data["parent_target_hash"] = data.pop("parent_prompt_hash")
        if not data.get('task_pack_id'):
            evidence = dict(data.get('evidence', ()))
            data['task_pack_id'] = evidence.get('Task package', '')
            data['task_pack_name'] = evidence.get('Task package name', data['task_pack_id'])
            data['task_pack_hash'] = evidence.get('Task package hash', '')
            # The host owns this frozen receipt, not a strategy-specific journal.
            reference = evidence.get('Task snapshot', '')
            if reference:
                raw = self.root.parent.parent.parent / reference
                allowed = self.root.parent / 'task-snapshots'
                if not raw.is_symlink() and raw.resolve().parent == allowed.resolve():
                    try:
                        encoded = raw.read_bytes()
                        if 'sha256:' + hashlib.sha256(encoded).hexdigest() == evidence.get('Task snapshot hash'):
                            receipt = json.loads(encoded)
                            task = receipt.get('task', {})
                            if task.get('cases_digest') == data['cases_digest']:
                                data['task_pack_id'] = task.get('pack_id', data['task_pack_id'])
                                data['task_pack_name'] = task.get('name') or dict(receipt.get('preview', ())).get('Cases') or data['task_pack_name']
                    except (OSError, ValueError, TypeError, AttributeError):
                        pass
        record = CandidateRecord(**data)
        if record.candidate_id != candidate_id:
            raise ValueError("candidate record identity mismatch")
        return record

    def list(self) -> tuple[CandidateRecord, ...]:
        if not self.root.is_dir():
            return ()
        records = [self.read(path.stem) for path in self.root.glob("*.json")]
        return tuple(sorted(records, key=lambda item: item.created_at, reverse=True))

    def update(self, candidate_id: str, *, status: str | None = None, notified: bool | None = None, activated_manifest_digest: str | None = None) -> CandidateRecord:
        old = self.read(candidate_id)
        record = replace(
            old,
            status=old.status if status is None else status,
            notified=old.notified if notified is None else notified,
            activated_manifest_digest=old.activated_manifest_digest if activated_manifest_digest is None else activated_manifest_digest,
        )
        self._write(record, create=False)
        return record

    def pending_notice(self) -> tuple[str, ...]:
        return tuple(
            record.candidate_id for record in self.list()
            if record.status == "proposed" and not record.notified
        )

    def _path(self, candidate_id: str) -> Path:
        if not isinstance(candidate_id, str) or not _CANDIDATE_ID.fullmatch(candidate_id):
            raise ValueError("candidate id must be 32 lowercase hex characters")
        return self.root / f"{candidate_id}.json"

    def _write(self, record: CandidateRecord, *, create: bool) -> None:
        path = self._path(record.candidate_id)
        self.root.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or (create and path.exists()):
            raise ValueError("candidate record path already exists or is a symlink")
        descriptor, temp_name = tempfile.mkstemp(prefix=".candidate-", dir=self.root)
        temp = Path(temp_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(asdict(record), stream, ensure_ascii=False, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)


def validate_candidate_text(text: str) -> None:
    if not isinstance(text, str) or not text.strip() or len(text) > 30_000:
        raise ValueError("Optimization candidate text must contain 1–30,000 characters")
    if any(ord(char) < 32 and char not in "\n\t" for char in text):
        raise ValueError("Optimization candidate text contains control characters")
