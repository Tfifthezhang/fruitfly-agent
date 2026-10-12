"""Freeze optimization receipts, run generic searches and persist proposals."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping
import uuid

from fruitfly_agent.run.storage.candidates import CandidateRecord
from fruitfly_agent.run.storage.results import save_task_result

class RunSearchJobs:
    """Own previews and coordinate evidence through injected runtime capabilities."""

    def __init__(self, *, workspace, artifacts, candidates, snapshots, active_manifest,
                 optimizer, target, task_catalog, selected_target, scope, compact):
        self.workspace = workspace
        self.artifacts = artifacts
        self.candidates = candidates
        self.snapshots = snapshots
        self.active_manifest = active_manifest
        self.optimizer = optimizer
        self.target = target
        self.task_catalog = task_catalog
        self.selected_target = selected_target
        self.scope = scope
        self.compact = compact
        self._previews = {}
        self._last_target = None

    def clear(self):
        self._previews.clear()
        self._last_target = None

    def last_target(self, manifest_digest=None):
        if self._last_target is not None and (manifest_digest is None or self._last_target[0] == manifest_digest):
            return self._last_target[1]
        return None

    async def optimize(
        self, active_manifest: Mapping[str, object], direction: str, *, preview_token: str = ""
    ) -> tuple[CandidateRecord, ...]:
        """Run the selected text optimizer and persist proposals for human review."""

        direction = direction.strip()
        if not direction or len(direction) > 500:
            raise ValueError("Optimization direction must contain 1–500 characters")
        manifest = self.active_manifest()
        if manifest is None or active_manifest.get("digest") != manifest.digest:
            raise RuntimeError("active runtime changed; start a new search")
        optimizer = self.optimizer(active_manifest)
        try:
            self.artifacts.root.relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError("optimization artifact store must stay inside the workspace") from exc
        if not preview_token:
            preview_token = self.optimization_preview(active_manifest, direction=direction).preview_token
        try:
            receipt = self._previews.pop(preview_token)
        except KeyError as exc:
            raise ValueError("unknown or consumed optimization preview; preview again") from exc
        parent, target_id, target_hash, confirmed_direction, task, snapshot_path, snapshot_hash = receipt
        if parent != manifest.digest or confirmed_direction != direction:
            raise ValueError("optimization request changed; preview again")
        target = self.target(active_manifest, target_id=target_id)
        snapshot = target.snapshot()
        if snapshot.content_hash != target_hash:
            raise ValueError("optimization target changed; preview again")
        if task and self.task_catalog().source_hash(task.pack_id) != task.source_hash:
            raise ValueError("task package changed; preview again")
        self.snapshots.verify(snapshot_path, snapshot_hash)
        proposals = await optimizer.search(snapshot.text, direction, parent_manifest=manifest.digest, task=task)
        proposals = tuple(replace(p, evidence=(*p.evidence, ("Task snapshot", str(snapshot_path.relative_to(self.workspace))), ("Task snapshot hash", snapshot_hash))) for p in proposals)
        if self.active_manifest() is not manifest:
            raise RuntimeError("active runtime changed during optimization")
        for proposal in proposals:
            target.validate(proposal.text)
        records = tuple(self.candidates.create(
            text=proposal.text, algorithm=proposal.algorithm,
            parent_manifest=manifest.to_dict(), cases_digest=proposal.cases_digest,
            direction=direction, seed_score=proposal.seed_score,
            validation_score=proposal.validation_score, metric_calls=proposal.metric_calls,
            evidence=proposal.evidence, snapshot=snapshot,
            config_path=self.scope()[0],
            profile_id=self.scope()[1],
            report=proposal.report,
            task_pack_id=task.pack_id if task else "", task_pack_name=task.name if task else "",
            task_pack_hash=task.source_hash if task else "",
        ) for proposal in proposals[:1])
        if records:
            for record in records:
                save_task_result(self.workspace, record, self.artifacts.read_text(record.artifact_id))
            self.compact()
        return records

    def optimization_preview(self, active_manifest: Mapping[str, object], *, pack_id=None, direction=""):
        optimizer = self.optimizer(active_manifest)
        task = None
        source = self.task_catalog()
        if pack_id is None and direction:
            pack_id = source.default_pack_id
        if pack_id:
            task = source.freeze(pack_id, self.selected_target())
        value = optimizer.preview(task=task) if task is not None else optimizer.preview()
        target = self.target(active_manifest, target_id=value.target_id).snapshot()
        if task and task.target_id != value.target_id:
            raise ValueError("optimizer target differs from task projection")
        self._last_target = (active_manifest.get("digest"), value.target_id)
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
        path, identity = self.snapshots.freeze(payload)
        token = uuid.uuid4().hex
        if len(self._previews) >= 16:
            self._previews.pop(next(iter(self._previews)))
        self._previews[token] = (active_manifest.get("digest"), value.target_id, target.content_hash, direction, task, path, identity)
        details = value.details if task is None else (*value.details, ("Task package", task.name), ("Task package hash", task.source_hash), ("Objective policy", task.policy_id))
        return replace(value, preview_token=token, details=details)


