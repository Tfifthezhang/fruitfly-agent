"""Freeze optimization receipts, run generic searches and persist proposals."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Mapping
import uuid

from .optimization import CandidateRecord
from .task_results import save_task_result

if TYPE_CHECKING:
    from .application import RunApplicationFactory


class RunSearchJobs:
    """Coordinate job evidence using the factory's exact active runtime."""

    def __init__(self, factory: RunApplicationFactory) -> None:
        self.factory = factory

    async def optimize(
        self, active_manifest: Mapping[str, object], direction: str, *, preview_token: str = ""
    ) -> tuple[CandidateRecord, ...]:
        """Run the selected text optimizer and persist proposals for human review."""

        direction = direction.strip()
        if not direction or len(direction) > 500:
            raise ValueError("Optimization direction must contain 1–500 characters")
        manifest = self.factory._current_runtime_manifest
        config = self.factory._current_runtime_config
        if manifest is None or config is None or active_manifest.get("digest") != manifest.digest:
            raise RuntimeError("active runtime changed; start a new search")
        optimizer = self.factory._optimizer(active_manifest)
        try:
            self.factory.artifact_store.root.relative_to(self.factory.cwd)
        except ValueError as exc:
            raise ValueError("optimization artifact store must stay inside the workspace") from exc
        if not preview_token:
            preview_token = self.factory.optimization_preview(active_manifest, direction=direction).preview_token
        try:
            receipt = self.factory._search_previews.pop(preview_token)
        except KeyError as exc:
            raise ValueError("unknown or consumed optimization preview; preview again") from exc
        parent, target_id, target_hash, confirmed_direction, task, snapshot_path, snapshot_hash = receipt
        if parent != manifest.digest or confirmed_direction != direction:
            raise ValueError("optimization request changed; preview again")
        target = self.factory._target(active_manifest, target_id=target_id)
        snapshot = target.snapshot()
        if snapshot.content_hash != target_hash:
            raise ValueError("optimization target changed; preview again")
        if task and self.factory.task_pack_catalog().source_hash(task.pack_id) != task.source_hash:
            raise ValueError("task package changed; preview again")
        self.factory._task_snapshots.verify(snapshot_path, snapshot_hash)
        proposals = await optimizer.search(snapshot.text, direction, parent_manifest=manifest.digest, task=task)
        proposals = tuple(replace(p, evidence=(*p.evidence, ("Task snapshot", str(snapshot_path.relative_to(self.factory.cwd))), ("Task snapshot hash", snapshot_hash))) for p in proposals)
        if self.factory._current_runtime_manifest is not manifest:
            raise RuntimeError("active runtime changed during optimization")
        for proposal in proposals:
            target.validate(proposal.text)
        records = tuple(self.factory.candidate_store.create(
            text=proposal.text, algorithm=proposal.algorithm,
            parent_manifest=manifest.to_dict(), cases_digest=proposal.cases_digest,
            direction=direction, seed_score=proposal.seed_score,
            validation_score=proposal.validation_score, metric_calls=proposal.metric_calls,
            evidence=proposal.evidence, snapshot=snapshot,
            config_path=str(self.factory._selection.config_path.resolve()),
            profile_id=self.factory._selection.profile.profile_id,
            report=proposal.report,
            task_pack_id=task.pack_id if task else "", task_pack_name=task.name if task else "",
            task_pack_hash=task.source_hash if task else "",
        ) for proposal in proposals[:1])
        if records:
            for record in records:
                save_task_result(self.factory.cwd, record, self.factory.artifact_store.read_text(record.artifact_id))
            self.factory.compact_candidates()
        return records


    def optimization_preview(self, active_manifest: Mapping[str, object], *, pack_id=None, direction=""):
        optimizer = self.factory._optimizer(active_manifest)
        task = None
        source = self.factory.task_pack_catalog()
        if pack_id is None and direction:
            pack_id = source.default_pack_id
        if pack_id:
            task = source.freeze(pack_id, self.factory.optimization_target_id())
        value = optimizer.preview(task=task) if task is not None else optimizer.preview()
        target = self.factory._target(active_manifest, target_id=value.target_id).snapshot()
        if task and task.target_id != value.target_id:
            raise ValueError("optimizer target differs from task projection")
        self.factory._last_optimization_target = (active_manifest.get("digest"), value.target_id)
        if not direction:
            return value
        direction = direction.strip()
        if not direction or len(direction) > 500:
            raise ValueError("direction must contain 1–500 characters")
        payload = {"parent_manifest": active_manifest, "target_hash": target.content_hash,
                   "direction": direction, "algorithm": value.algorithm,
                   "preview": value.details,
                   "task": None if task is None else {"pack_id": task.pack_id, "name": task.name, "source_hash": task.source_hash,
                       "material_files": task.material_files, "cases_digest": task.digest, "policy_id": task.policy_id, "task_execution_id": task.execution_id, "case_sources": task.case_sources, "train": [{"input": c.input, "expected": c.expected, "verification": c.verification} for c in task.train],
                       "validation": [{"input": c.input, "expected": c.expected, "verification": c.verification} for c in task.validation]}}
        path, identity = self.factory._task_snapshots.freeze(payload)
        token = uuid.uuid4().hex
        if len(self.factory._search_previews) >= 16:
            self.factory._search_previews.pop(next(iter(self.factory._search_previews)))
        self.factory._search_previews[token] = (active_manifest.get("digest"), value.target_id, target.content_hash, direction, task, path, identity)
        details = value.details if task is None else (*value.details, ("Task package", task.name), ("Task package hash", task.source_hash), ("Objective policy", task.policy_id))
        return replace(value, preview_token=token, details=details)


