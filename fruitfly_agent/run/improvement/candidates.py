"""Candidate business rules over explicit storage, configuration, and runtime ports."""
from __future__ import annotations

from dataclasses import replace
import difflib
from pathlib import Path
from typing import Callable, Mapping

from fruitfly_agent.run.storage.prompts import resolve_base_prompt
from fruitfly_agent.run.storage.candidates import CandidateRecord
from fruitfly_agent.run.storage.retention import compact_candidates
from fruitfly_agent.run.runtime.activation import bind_activation
from fruitfly_agent.run.configuration.operations import BindingEditor
from fruitfly_agent.lab.improvement.targets.text import expand_target


class RunCandidates:
    def __init__(self, *, workspace, store, artifacts, scope, profile, resolved_profile,
                 configuration: Callable[[], BindingEditor], active_manifest, active_profile, target, pinned_bindings,
                 prepare_runtime, reload_configuration, version_guard=None, activation_guard=None):
        self.workspace = workspace
        self.store = store
        self.artifacts = artifacts
        self.scope = scope
        self.profile = profile
        self.resolved_profile = resolved_profile
        self.configuration = configuration
        self.active_manifest = active_manifest
        self.active_profile = active_profile
        self.target = target
        self.pinned_bindings = dict(pinned_bindings)
        self.prepare_runtime = prepare_runtime
        self.reload_configuration = reload_configuration
        self.version_guard = version_guard
        self.activation_guard = activation_guard

    def check_version(self, record):
        target = self.target(record.target)
        if target is None or target.snapshot().role != record.role:
            raise ValueError('candidate role differs from the registered target')
        if record.role != 'H' and record.role not in getattr(target, 'adoption_roles', ()):
            raise ValueError('this host has no adoption adapter for this role')
        if self.version_guard is not None:
            self.version_guard(record)

    def reconcile(self, manifest, targets):
        """Reconcile saved intent only after a fresh runtime actually activates."""
        try:
            for candidate in self.store.list():
                scope = self.scope()
                if not candidate.config_path and manifest.digest in {
                        candidate.parent_manifest_digest, candidate.activated_manifest_digest}:
                    candidate = replace(candidate, config_path=scope[0], profile_id=scope[1])
                    self.store.replace_record(candidate)
                if (candidate.config_path, candidate.profile_id) != scope:
                    continue
                target = targets.get(candidate.target)
                if target is not None and candidate.status == "selected_for_next_session":
                    if candidate.artifact_id == target.snapshot().content_hash:
                        if self.activation_guard is not None:
                            self.activation_guard(candidate, manifest.to_dict())
                        self.store.update(candidate.candidate_id, status="adopted",
                                          activated_manifest_digest=manifest.digest)
            self.compact_candidates()
        except (OSError, TypeError, ValueError):
            pass

    def compact_candidates(self):
        return compact_candidates(self.workspace, self.store, Path(self.scope()[0]))

    def candidates(self) -> tuple[CandidateRecord, ...]:
        config = str(Path(self.scope()[0]).resolve())
        profile = self.scope()[1]
        latest: dict[tuple[str, str, str], CandidateRecord] = {}
        for record in self.store.list():
            if (record.config_path, record.profile_id) == (config, profile) or (
                    not record.config_path and self.active_manifest() is not None
                    and self.active_manifest().digest in {record.parent_manifest_digest, record.activated_manifest_digest}):
                latest.setdefault((record.role, record.target, record.task_pack_id), record)
        return tuple(latest.values())

    def candidate_notice(self) -> tuple[str, ...]:
        return tuple(r.candidate_id for r in self.candidates() if r.status == 'proposed' and not r.notified)

    def acknowledge_candidate_notice(self, candidate_ids: tuple[str, ...]) -> None:
        for candidate_id in candidate_ids:
            self.store.update(candidate_id, notified=True)

    def candidate_detail(self, candidate_id: str) -> tuple[CandidateRecord, str]:
        record = self.store.read(candidate_id)
        parent = self.artifacts.read_text(record.parent_target_reference) if record.parent_target_reference.startswith("sha256:") else resolve_base_prompt(record.parent_target_reference, self.artifacts)[0]
        new = self.artifacts.read_text(record.artifact_id)
        diff = '\n'.join(difflib.unified_diff(
            parent.splitlines(), new.splitlines(),
            fromfile=f'parent {record.target}', tofile='Improvement candidate', lineterm='',
        ))
        return record, diff

    def candidate_action(
        self, active_manifest: Mapping[str, object], candidate_id: str, action: str
    ) -> CandidateRecord:
        record = self.store.read(candidate_id)
        self.check_scope(record)
        if action in {"review", "defer", "reject"}:
            if record.status not in {"proposed", "reviewed", "deferred"}:
                operation = "reviewed" if action == "review" else "deferred or rejected"
                raise ValueError(f"candidate can no longer be {operation}")
            status = {"review": "reviewed", "defer": "deferred", "reject": "rejected"}[action]
            return self.store.update(candidate_id, status=status)
        if action != "adopt":
            raise ValueError("candidate action must be review, defer, reject or adopt")
        manifest = self.active_manifest()
        if manifest is None or active_manifest.get("digest") != manifest.digest:
            raise RuntimeError("active runtime changed before candidate adoption")
        if record.status not in {"proposed", "reviewed", "deferred"}:
            raise ValueError("candidate is no longer adoptable")
        self.check_version(record)
        if record.parent_manifest_digest != manifest.digest:
            self.store.update(candidate_id, status="stale")
            raise ValueError("candidate parent version is stale; search again")
        current = self.resolved_profile()
        if current != self.profile() or self.configuration().changed:
            raise ValueError("configuration changed; resolve it before adopting a candidate")
        target = self.target(record.target)
        if target is None or target.snapshot().content_hash != record.parent_target_hash:
            self.store.update(candidate_id, status="stale")
            raise ValueError("target changed; search again")
        snapshot = target.snapshot()
        if snapshot.binding.kind != record.binding_kind or snapshot.binding.key != record.binding_key:
            raise ValueError("candidate target binding changed")
        target.validate(self.artifacts.read_text(record.artifact_id))
        bindings = self.candidate_bindings(record)
        try:
            for kind, key, reference in bindings:
                self.configuration().bind_target(kind, key, reference)
            self.configuration().save()
        except BaseException:
            self.configuration().reset()
            raise
        return self.store.update(candidate_id, status="selected_for_next_session")

    def check_scope(self, record):
        scope = (str(Path(self.scope()[0]).resolve()), self.scope()[1])
        if record.config_path and (record.config_path, record.profile_id) != scope:
            raise ValueError('candidate belongs to another configuration/profile')

    def _saved_candidate_profile(self, record):
        return self.apply_candidate(self.profile(), record)

    def candidate_bindings(self, record):
        """Expand object-owned component content into existing profile bindings."""
        target = self.target(record.target)
        if target is None:
            raise ValueError('candidate target is unavailable')
        text = self.artifacts.read_text(record.artifact_id)
        target.validate(text)
        snapshot = target.snapshot()
        if snapshot.binding.kind == 'components':
            original = dict((part.target_id, value) for part, value in expand_target(
                snapshot, self.artifacts.read_text(record.parent_target_reference)))
            parts = tuple((part, value) for part, value in expand_target(snapshot, text)
                          if value != original[part.target_id])
        else:
            parts = expand_target(snapshot, text)
        if not parts:
            raise ValueError('candidate does not change any component')
        result = []
        for part, value in parts:
            owner = self.target(part.target_id)
            export = getattr(owner, 'export_text', None)
            if export is not None:
                value = export(value)
            reference = self.artifacts.put_text(value).artifact_id
            binding = part.binding
            if (binding.kind == 'artifact' and binding.key in self.pinned_bindings
                    and self.pinned_bindings[binding.key] != reference):
                raise ValueError('target is pinned by constructor bindings; update those bindings before adoption')
            result.append((binding.kind, binding.key, reference))
        return tuple(result)

    def apply_candidate(self, profile, record):
        for kind, key, reference in self.candidate_bindings(record):
            if kind == 'configuration':
                from fruitfly_agent.runtime_spec import apply_profile_binding
                profile = apply_profile_binding(profile, kind, key, self.artifacts.read_text(reference))
            else:
                profile = (replace(profile, prompt=reference) if kind == 'prompt' else
                           replace(profile, artifact_bindings={**profile.artifact_bindings, key: reference}))
        return profile

    def candidate_profile(self, active_manifest, candidate_id):
        """Validate one candidate against the exact active parent and binding."""
        record = self.store.read(candidate_id)
        self.check_scope(record)
        if record.status not in {"proposed", "reviewed", "deferred", "selected_for_next_session"}:
            raise ValueError("candidate is no longer adoptable")
        self.check_version(record)
        if self.active_manifest() is None or active_manifest.get("digest") != self.active_manifest().digest or record.parent_manifest_digest != active_manifest.get("digest"):
            raise ValueError("candidate parent version is stale")
        target = self.target(record.target)
        if target is None or target.snapshot().content_hash != record.parent_target_hash:
            raise ValueError("candidate target is stale")
        snapshot = target.snapshot()
        if (record.binding_kind, record.binding_key) != (snapshot.binding.kind, snapshot.binding.key):
            raise ValueError("candidate binding differs from target")
        target.validate(self.artifacts.read_text(record.artifact_id))
        profile = self.apply_candidate(self.active_profile() or self.profile(), record)
        resolved_profile = self.resolved_profile()
        unchanged = resolved_profile == self.profile() and not self.configuration().changed
        saved_candidate = record.status == "selected_for_next_session" and resolved_profile == self._saved_candidate_profile(record)
        if not (unchanged or saved_candidate):
            raise ValueError("configuration changed before candidate activation")
        return record, profile

    async def prepare_candidate(self, active_manifest, candidate_id):
        """Prepare an isolated candidate without changing saved or active selection."""
        record, profile = self.candidate_profile(active_manifest, candidate_id)
        handle = await self.prepare_runtime(profile)
        def activate():
            # Recheck after potentially asynchronous startup, before persistence.
            self.check_version(record)
            if self.activation_guard is not None:
                self.activation_guard(record, handle.manifest)
            current_profile = self.resolved_profile()
            valid_current = current_profile == self.profile() and not self.configuration().changed
            valid_saved = record.status == "selected_for_next_session" and current_profile == self._saved_candidate_profile(record)
            if not (valid_current or valid_saved):
                raise ValueError("configuration changed while preparing candidate")
            if not valid_saved:
                # Persist the recoverable intent first. If the process exits
                # after profile save, the next successful startup reconciles it
                # against the actual target hash and manifest.
                self.store.update(candidate_id, status="selected_for_next_session")
                for kind, key, reference in self.candidate_bindings(record):
                    self.configuration().bind_target(kind, key, reference)
                try:
                    self.configuration().save()
                except BaseException:
                    self.configuration().reset()
                    self.store.update(candidate_id, status=record.status)
                    raise
                self.reload_configuration()
            self.store.update(candidate_id, status="adopted", activated_manifest_digest=handle.manifest["digest"])
        bind_activation(handle, before=activate)
        return handle


