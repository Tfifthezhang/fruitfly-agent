"""Freeze improvement receipts, run generic searches and persist proposals."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping
import uuid

from fruitfly_agent.lab.improvement.api import method_identity
from fruitfly_agent.run.storage.candidates import CandidateRecord
from fruitfly_agent.run.storage.results import save_task_result

class RunSearchJobs:
    """Own previews and coordinate evidence through injected runtime capabilities."""

    def __init__(self, *, workspace, artifacts, candidates, snapshots, active_manifest,
                 improver, target, task_catalog, selected_target, scope, compact,
                 freeze_version=None, candidate_version=None, select_method=None, remember_method=None,
                 release_method=None):
        self.select_method = select_method
        self.remember_method, self.release_method = remember_method, release_method
        self.running_improver = None
        self.workspace = workspace
        self.artifacts = artifacts
        self.candidates = candidates
        self.snapshots = snapshots
        self.active_manifest = active_manifest
        self.improver = improver
        self.target = target
        self.task_catalog = task_catalog
        self.selected_target = selected_target
        self.scope = scope
        self.compact = compact
        self._previews = {}
        self._last_target = None
        self.freeze_version, self.candidate_version = freeze_version, candidate_version

    def clear(self):
        self._previews.clear()
        self._last_target = None

    def last_target(self, manifest_digest=None):
        if self._last_target is not None and (manifest_digest is None or self._last_target[0] == manifest_digest):
            return self._last_target[1]
        return None

    async def improve(
        self, active_manifest: Mapping[str, object], direction: str, *, preview_token: str = ""
    ) -> tuple[CandidateRecord, ...]:
        """Run the selected text improver and persist proposals for human review."""

        direction = direction.strip()
        if not direction or len(direction) > 500:
            raise ValueError("Improvement direction must contain 1–500 characters")
        manifest = self.active_manifest()
        if manifest is None or active_manifest.get("digest") != manifest.digest:
            raise RuntimeError("active runtime changed; start a new search")
        self.improver(active_manifest)
        try:
            self.artifacts.root.relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError("improvement artifact store must stay inside the workspace") from exc
        if not preview_token:
            preview_token = self.improvement_preview(active_manifest, direction=direction).preview_token
        try:
            receipt = self._previews.pop(preview_token)
        except KeyError as exc:
            raise ValueError("unknown or consumed improvement preview; preview again") from exc
        parent, target_id, target_hash, confirmed_direction, task, snapshot_path, snapshot_hash, system_version, improver, confirmed_method, source = receipt
        if method_identity(improver) != confirmed_method:
            raise ValueError("improvement method changed; preview again")
        if parent != manifest.digest or confirmed_direction != direction:
            raise ValueError("improvement request changed; preview again")
        if system_version is not None and self.freeze_version() != system_version:
            raise ValueError('parent H/S/I changed; preview again')
        target = self.target(active_manifest, target_id=target_id)
        snapshot = target.snapshot()
        if snapshot.content_hash != target_hash or snapshot.role not in {'H', *getattr(target, 'adoption_roles', ())}:
            raise ValueError("improvement target changed; preview again")
        if task and source.source_hash(task.pack_id) != task.source_hash:
            raise ValueError("task package changed; preview again")
        self.snapshots.verify(snapshot_path, snapshot_hash)
        self.running_improver = improver
        try:
            if self.remember_method is not None:
                self.remember_method(improver)
            proposals = await improver.search(snapshot.text, direction, parent_manifest=manifest.digest, task=task)
        finally:
            self.running_improver = None
            if self.release_method is not None:
                self.release_method(improver)
        if method_identity(improver) != confirmed_method:
            raise ValueError("improvement method changed during search")
        proposals = tuple(replace(p, evidence=(*p.evidence, ("Task snapshot", str(snapshot_path.relative_to(self.workspace))), ("Task snapshot hash", snapshot_hash))) for p in proposals)
        if self.active_manifest() is not manifest:
            raise RuntimeError("active runtime changed during improvement")
        if system_version is not None and self.freeze_version() != system_version:
            raise ValueError('parent H/S/I changed during improvement')
        for proposal in proposals:
            target.validate(proposal.text)
        if system_version is not None:
            bound = []
            for proposal in proposals:
                version = self.candidate_version(system_version, snapshot, proposal.text)
                bound.append(replace(proposal, evidence=(*proposal.evidence,
                    ('Parent system version', system_version.version_id),
                    ('Candidate system version', version.version.version_id),
                    ('Version candidate', version.candidate_id))))
            proposals = tuple(bound)
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

    def improvement_preview(self, active_manifest: Mapping[str, object], *, pack_id=None, direction="",
                            method_id=None, target_id=None, parameters=None):
        improver = self.improver(active_manifest)
        if self.select_method is not None and (method_id is not None or target_id is not None or parameters is not None):
            improver = self.select_method(method_id=method_id, target_id=target_id, parameters=parameters)
        elif method_id is not None or target_id is not None or parameters:
            raise ValueError('this host does not support per-job method selection')
        try:
            task = None
            source = getattr(improver, "task_source", None) or self.task_catalog()
            if pack_id is None and direction:
                pack_id = source.default_pack_id
            if pack_id:
                task = source.freeze(pack_id, target_id or self.selected_target())
            value = improver.preview(task=task) if task is not None else improver.preview()
            target = self.target(active_manifest, target_id=value.target_id).snapshot()
            if value.role != target.role:
                raise ValueError('search method and target H/S/I roles differ')
            if target_id is not None and value.target_id != target_id:
                raise ValueError('bound method differs from the selected target')
            if method_id is not None and value.algorithm != method_id:
                raise ValueError('bound method differs from the selected algorithm')
            if task and task.target_id != value.target_id:
                raise ValueError("improver target differs from task projection")
            self._last_target = (active_manifest.get("digest"), value.target_id)
            if not direction:
                if self.release_method is not None:
                    self.release_method(improver)
                return value
            direction = direction.strip()
            if not direction or len(direction) > 500:
                raise ValueError("direction must contain 1–500 characters")
            payload = {"parent_manifest": active_manifest, "target_hash": target.content_hash,
                       "direction": direction, "algorithm": value.algorithm,
                       "preview": value.details, "method_identity": method_identity(improver),
                       "task": None if task is None else {"pack_id": task.pack_id, "name": task.name, "source_hash": task.source_hash,
                           "material_files": task.material_files, "cases_digest": task.digest, "policy_id": task.policy_id, "task_execution_id": task.execution_id, "case_sources": task.case_sources, "train": [{"input": c.input, "expected": c.expected, "verification": c.verification} for c in task.train],
                           "validation": [{"input": c.input, "expected": c.expected, "verification": c.verification} for c in task.validation]}}
            system_version = self.freeze_version() if self.freeze_version is not None else None
            if system_version is not None:
                payload['parent_system_version'] = system_version.to_dict()
            path, identity = self.snapshots.freeze(payload)
            token = uuid.uuid4().hex
            if len(self._previews) >= 16:
                expired = self._previews.pop(next(iter(self._previews)))
                if self.release_method is not None:
                    self.release_method(expired[8])
            self._previews[token] = (active_manifest.get("digest"), value.target_id, target.content_hash, direction, task, path, identity, system_version, improver, method_identity(improver), source)
            details = (*value.details, ('Improvement role', target.role)) if task is None else (*value.details, ('Improvement role', target.role), ("Task package", task.name), ("Task package hash", task.source_hash), ("Objective policy", task.policy_id))
            if system_version is not None:
                details = (*details, ('Parent H/S/I', system_version.version_id))
            return replace(value, preview_token=token, details=details)


        except BaseException:
            if self.release_method is not None:
                self.release_method(improver)
            raise
