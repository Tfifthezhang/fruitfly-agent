"""Concrete application factory for the profile-driven local harness."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import difflib
from inspect import isawaitable
import uuid
from pathlib import Path
from typing import Mapping

from fruitfly_agent.core.errors import SessionCorruptError
from fruitfly_agent.core.session.storage import Session
from fruitfly_agent.interactive import (
    InteractiveMechanism,
    InteractiveSession,
    ResumableSession,
)
from fruitfly_agent.interactive.application import RuntimeHandle
from fruitfly_agent.lab.algorithms.targets import TEXT_TARGET_PREFIX, TextTarget
from fruitfly_agent.lab.catalog import LabCatalog, builtin_catalog
from fruitfly_agent.lab.base_prompt import DEFAULT_PROMPT, DEFAULT_PROMPT_ID
from fruitfly_agent.lab.optimization.text_optimizer import TEXT_OPTIMIZER_COMPONENT, TEXT_OPTIMIZATION_TARGET_COMPONENT, TextOptimizer, SearchActivitySource
from fruitfly_agent.lab.optimization.task_packs import TASK_PACK_COMPONENT, TaskSnapshotStore
from fruitfly_agent.providers.registry import ProviderRegistry

from .optimization_service import RunOptimizationService

from .assembly import RuntimeAssembly, build_runtime, resolve_base_prompt
from .artifacts import DataArtifactStore
from .optimization import CandidateRecord, CandidateStore
from .profiles import (
    HarnessSelection,
    RunConfigurationController,
    _display_section,
    display_group,
    resolve_harness_selection,
    resolve_profile_models,
)


_RUNTIME_MANIFEST_KIND = "runtimeManifest"


class RunApplicationFactory:
    """Resolve settings and open exact, session-bound runtime instances."""

    def __init__(
        self,
        *,
        cwd: Path,
        environment: Mapping[str, str],
        config_path: str | None = None,
        profile_id: str | None = None,
        catalog: LabCatalog | None = None,
        provider_registry: ProviderRegistry | None = None,
        data_artifact_bindings: Mapping[str, str] | None = None,
        allow_incomplete: bool = False,
        task_pack_sources: tuple = (),
    ) -> None:
        self.cwd = cwd.resolve()
        self.task_pack_sources = tuple(task_pack_sources)
        self._task_snapshots = TaskSnapshotStore(self.cwd)
        self._search_previews = {}
        self._last_optimization_target = None
        self.environment = dict(environment)
        self._requested_config_path = config_path
        self._requested_profile_id = profile_id
        self.catalog = catalog or builtin_catalog()
        self.provider_registry = provider_registry
        self.data_artifact_bindings = dict(data_artifact_bindings or {})
        self.artifact_store = DataArtifactStore(self.cwd / ".fruitfly" / "artifacts")
        candidate_root = (self.cwd / ".fruitfly" / "optimization" / "candidates").resolve()
        try:
            candidate_root.relative_to(self.cwd)
        except ValueError as exc:
            raise ValueError("candidate store must stay inside the workspace") from exc
        self.candidate_store = CandidateStore(
            candidate_root,
            self.artifact_store,
        )
        self._allow_incomplete = allow_incomplete
        self._stock_catalog = catalog is None
        self._current_runtime_manifest = None
        self._current_components = {}
        self._current_runtime_config = None
        self._current_optimizer: TextOptimizer | None = None
        self._active_profile = None
        self._current_targets: dict[str, TextTarget] = {}
        self._selection = self._resolve()
        self._configuration = RunConfigurationController(
            self._selection,
            self.catalog,
            self.artifact_store,
        )

    @property
    def selection(self) -> HarnessSelection:
        return self._selection

    @property
    def configuration(self) -> RunConfigurationController:
        return self._configuration

    def reload_configuration(self) -> None:
        self._requested_config_path = str(self._selection.config_path)
        self._requested_profile_id = None
        self._allow_incomplete = False
        self._selection = self._resolve()
        self._configuration = RunConfigurationController(
            self._selection,
            self.catalog,
            self.artifact_store,
        )

    def new_session_path(self) -> Path:
        return new_session_path(self.cwd)

    def resumable_sessions(
        self,
        *,
        current_path: Path,
        manifest_digest: str,
    ) -> tuple[ResumableSession, ...]:
        accepted = {manifest_digest}
        manifest = self._current_runtime_manifest
        if self._stock_catalog and _known_legacy_default() and manifest is not None and manifest.digest == manifest_digest and not any("implementation_id" in item for item in manifest.components):
            if manifest.base_prompt["reference"] == DEFAULT_PROMPT_ID:
                accepted.add(manifest.legacy_dict(4 if manifest.data_artifacts else 3)["digest"])
        return discover_resumable_sessions(
            self.cwd,
            current_path=current_path,
            manifest_digests=accepted,
        )

    async def open(
        self,
        *,
        resume: bool,
        session_path: Path | None,
        profile_override=None,
    ) -> RuntimeHandle:
        selection = self._selection if profile_override is None else replace(self._selection, profile=profile_override)
        resolve_profile_models(selection.profile, selection.config_path)
        path = session_path or self.new_session_path()
        session = Session(path)
        resources: list[object] = []
        try:
            messages = session.messages() if resume else []
            if resume and not messages:
                raise ValueError("nothing to resume")
            artifact_bindings = {**selection.profile.artifact_bindings, **self.data_artifact_bindings}
            if resume:
                saved_bindings = _session_artifact_bindings(session)
                if saved_bindings:
                    if self.data_artifact_bindings and self.data_artifact_bindings != saved_bindings:
                        raise ValueError(
                            "runtime data artifact bindings differ from this session"
                        )
                    artifact_bindings = saved_bindings
            profile = selection.profile
            if resume:
                saved_prompt = _session_prompt_reference(session)
                if saved_prompt is not None:
                    profile = replace(profile, prompt=saved_prompt)
            runtime = build_runtime(
                profile,
                config_path=selection.config_path,
                catalog=self.catalog,
                environment=self.environment,
                session=session,
                cwd=self.cwd,
                provider_registry=self.provider_registry,
                resource_sink=resources,
                artifact_store=self.artifact_store,
                artifact_bindings=artifact_bindings,
                task_pack_sources=self.task_pack_sources,
            )
            check_session_manifest(
                session, runtime, resume=resume,
                allow_legacy_default_prompt=self._stock_catalog,
            )
            record_session_manifest(session, runtime)
            visible_mechanism_ids = tuple(
                mechanism_id
                for mechanism_id in runtime.mechanism_ids
                if self.catalog.get(mechanism_id).visible
            )
            details = tuple(
                InteractiveMechanism(
                    mechanism_id,
                    display_group(self.catalog.get(mechanism_id).descriptor),
                    self.catalog.get(mechanism_id).descriptor.label,
                    self.catalog.get(mechanism_id).descriptor.primary.layer,
                    self.catalog.get(mechanism_id).descriptor.primary.family,
                    self.catalog.get(mechanism_id).descriptor.primary.context_phase,
                    _display_section(self.catalog.get(mechanism_id).descriptor),
                )
                for mechanism_id in visible_mechanism_ids
            )
            tool_categories: dict[str, str] = {}
            for mechanism_id in runtime.component_ids:
                descriptor = self.catalog.get(mechanism_id).descriptor
                tool_categories.update({name: "tools" for name in descriptor.effects.tools})
            interaction = InteractiveSession(
                runtime.config,
                context_pipeline=runtime.context_pipeline,
                messages=messages,
                working_directory=self.cwd,
                session_path=path,
                mechanisms=visible_mechanism_ids,
                mechanism_details=details,
                tool_categories=tool_categories,
            )
            optimization_service = RunOptimizationService(self)
            handle = RuntimeHandle(
                session=interaction,
                manifest=runtime.manifest.to_dict(),
                components=runtime.components,
                close_callback=session.close,
                optimization=optimization_service,
                candidate_activation=optimization_service,
            )
            optimizer = runtime.components.get(TEXT_OPTIMIZER_COMPONENT)
            if optimizer is not None and not isinstance(optimizer, TextOptimizer):
                raise TypeError("text-optimizer component must implement TextOptimizer")
            targets = {key[len(TEXT_TARGET_PREFIX):]: value for key, value in runtime.components.items()
                       if key.startswith(TEXT_TARGET_PREFIX)}
            if any(not isinstance(value, TextTarget) for value in targets.values()):
                raise TypeError("named text targets must implement TextTarget")

            def activate():
                self._active_profile = profile
                self._current_runtime_manifest = runtime.manifest
                self._current_components = runtime.components
                self._search_previews.clear()
                self._last_optimization_target = None
                self._current_runtime_config = runtime.config
                self._current_optimizer = optimizer
                self._current_targets = targets
                if not resume:
                    try:
                        for candidate in self.candidate_store.list():
                            scope = (str(self._selection.config_path.resolve()), self._selection.profile.profile_id)
                            if not candidate.config_path and runtime.manifest.digest in {
                                    candidate.parent_manifest_digest, candidate.activated_manifest_digest}:
                                candidate = replace(candidate, config_path=scope[0], profile_id=scope[1])
                                self.candidate_store._write(candidate, create=False)
                            if (candidate.config_path, candidate.profile_id) != scope:
                                continue
                            target = targets.get(candidate.target)
                            if target is not None and candidate.status == "selected_for_next_session":
                                if candidate.artifact_id == target.snapshot().content_hash:
                                    self.candidate_store.update(candidate.candidate_id, status="adopted", activated_manifest_digest=runtime.manifest.digest)
                        self.compact_candidates()
                    except (OSError, TypeError, ValueError):
                        pass
            handle.activate_callback = activate
            return handle
        except BaseException:
            await _close_resources(resources)
            session.close()
            raise

    def _resolve(self) -> HarnessSelection:
        return resolve_harness_selection(
            cwd=self.cwd,
            config_path=self._requested_config_path,
            profile_id=self._requested_profile_id,
            environment=self.environment,
            catalog=self.catalog,
            allow_incomplete=self._allow_incomplete,
        )

    async def optimize(
        self, active_manifest: Mapping[str, object], direction: str, *, preview_token: str = ""
    ) -> tuple[CandidateRecord, ...]:
        """Run the selected text optimizer and persist proposals for human review."""

        direction = direction.strip()
        if not direction or len(direction) > 500:
            raise ValueError("Optimization direction must contain 1–500 characters")
        manifest = self._current_runtime_manifest
        config = self._current_runtime_config
        if manifest is None or config is None or active_manifest.get("digest") != manifest.digest:
            raise RuntimeError("active runtime changed; start a new search")
        optimizer = self._optimizer(active_manifest)
        try:
            self.artifact_store.root.relative_to(self.cwd)
        except ValueError as exc:
            raise ValueError("optimization artifact store must stay inside the workspace") from exc
        if not preview_token:
            preview_token = self.optimization_preview(active_manifest, direction=direction).preview_token
        try:
            receipt = self._search_previews.pop(preview_token)
        except KeyError as exc:
            raise ValueError("unknown or consumed optimization preview; preview again") from exc
        parent, target_id, target_hash, confirmed_direction, task, snapshot_path, snapshot_hash = receipt
        if parent != manifest.digest or confirmed_direction != direction:
            raise ValueError("optimization request changed; preview again")
        target = self._target(active_manifest, target_id=target_id)
        snapshot = target.snapshot()
        if snapshot.content_hash != target_hash:
            raise ValueError("optimization target changed; preview again")
        if task and self.task_pack_catalog().source_hash(task.pack_id) != task.source_hash:
            raise ValueError("task package changed; preview again")
        self._task_snapshots.verify(snapshot_path, snapshot_hash)
        proposals = await optimizer.search(snapshot.text, direction, parent_manifest=manifest.digest, task=task)
        proposals = tuple(replace(p, evidence=(*p.evidence, ("Task snapshot", str(snapshot_path.relative_to(self.cwd))), ("Task snapshot hash", snapshot_hash))) for p in proposals)
        if self._current_runtime_manifest is not manifest:
            raise RuntimeError("active runtime changed during optimization")
        for proposal in proposals:
            target.validate(proposal.text)
        records = tuple(self.candidate_store.create(
            text=proposal.text, algorithm=proposal.algorithm,
            parent_manifest=manifest.to_dict(), cases_digest=proposal.cases_digest,
            direction=direction, seed_score=proposal.seed_score,
            validation_score=proposal.validation_score, metric_calls=proposal.metric_calls,
            evidence=proposal.evidence, snapshot=snapshot,
            config_path=str(self._selection.config_path.resolve()),
            profile_id=self._selection.profile.profile_id,
            report=proposal.report,
            task_pack_id=task.pack_id if task else "", task_pack_name=task.name if task else "",
            task_pack_hash=task.source_hash if task else "",
        ) for proposal in proposals[:1])
        if records:
            from .task_results import save_task_result
            for record in records:
                save_task_result(self.cwd, record, self.artifact_store.read_text(record.artifact_id))
            self.compact_candidates()
        return records

    def compact_candidates(self):
        from .retention import compact_candidates
        return compact_candidates(self.cwd, self.candidate_store, self._selection.config_path)

    def optimization_activity(self):
        optimizer = self._current_optimizer
        return optimizer.progress() if isinstance(optimizer, SearchActivitySource) else None

    def cancel_optimization(self) -> bool:
        return self._current_optimizer.cancel() if self._current_optimizer is not None else False

    def _target(self, active_manifest, *, target_id=None):
        if target_id is None:
            if self._last_optimization_target and self._last_optimization_target[0] == active_manifest.get("digest"):
                target_id = self._last_optimization_target[1]
            else:
                target_id = self._optimizer(active_manifest).preview().target_id
        try:
            target = self._current_targets[target_id]
            snapshot = target.snapshot()
            if snapshot.target_id != target_id or snapshot.schema != "text-v1":
                raise ValueError("target identity or text schema mismatch")
            return target
        except KeyError as exc:
            raise ValueError(f"optimization target {target_id!r} is not enabled") from exc

    def optimization_target_id(self):
        target_id = self._current_components.get(TEXT_OPTIMIZATION_TARGET_COMPONENT)
        if target_id is None and self._last_optimization_target is not None:
            target_id = self._last_optimization_target[1]
        if target_id is None and self._current_optimizer is not None:
            target_id = self._current_optimizer.preview().target_id
        return target_id or next(iter(self._current_targets))

    def task_pack_catalog(self):
        if self._current_runtime_config is None:
            raise RuntimeError("no active runtime")
        source = self._current_components.get(TASK_PACK_COMPONENT)
        if source is None:
            raise RuntimeError("this runtime has no task package catalog")
        return source

    def optimization_preview(self, active_manifest: Mapping[str, object], *, pack_id=None, direction=""):
        optimizer = self._optimizer(active_manifest)
        task = None
        source = self.task_pack_catalog()
        if pack_id is None and direction:
            pack_id = source.default_pack_id
        if pack_id:
            task = source.freeze(pack_id, self.optimization_target_id())
        value = optimizer.preview(task=task) if task is not None else optimizer.preview()
        target = self._target(active_manifest, target_id=value.target_id).snapshot()
        if task and task.target_id != value.target_id:
            raise ValueError("optimizer target differs from task projection")
        self._last_optimization_target = (active_manifest.get("digest"), value.target_id)
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
        path, identity = self._task_snapshots.freeze(payload)
        token = uuid.uuid4().hex
        if len(self._search_previews) >= 16:
            self._search_previews.pop(next(iter(self._search_previews)))
        self._search_previews[token] = (active_manifest.get("digest"), value.target_id, target.content_hash, direction, task, path, identity)
        details = value.details if task is None else (*value.details, ("Task package", task.name), ("Task package hash", task.source_hash), ("Objective policy", task.policy_id))
        return replace(value, preview_token=token, details=details)

    def _optimizer(self, active_manifest: Mapping[str, object]) -> TextOptimizer:
        manifest = self._current_runtime_manifest
        if manifest is None or active_manifest.get("digest") != manifest.digest:
            raise RuntimeError("active runtime changed; start a new Session")
        if self._current_optimizer is None:
            raise RuntimeError("text optimization is not enabled in the active Session; select it in /config first")
        return self._current_optimizer

    def candidates(self) -> tuple[CandidateRecord, ...]:
        config = str(self._selection.config_path.resolve())
        profile = self._selection.profile.profile_id
        latest = {}
        for record in self.candidate_store.list():
            if (record.config_path, record.profile_id) == (config, profile) or (
                    not record.config_path and self._current_runtime_manifest is not None
                    and self._current_runtime_manifest.digest in {record.parent_manifest_digest, record.activated_manifest_digest}):
                latest.setdefault((record.target, record.task_pack_id), record)
        return tuple(latest.values())

    def candidate_notice(self) -> tuple[str, ...]:
        return tuple(r.candidate_id for r in self.candidates() if r.status == 'proposed' and not r.notified)

    def acknowledge_candidate_notice(self, candidate_ids: tuple[str, ...]) -> None:
        for candidate_id in candidate_ids:
            self.candidate_store.update(candidate_id, notified=True)

    def candidate_detail(self, candidate_id: str) -> tuple[CandidateRecord, str]:
        record = self.candidate_store.read(candidate_id)
        parent = self.artifact_store.read_text(record.parent_target_reference) if record.parent_target_reference.startswith("sha256:") else resolve_base_prompt(record.parent_target_reference, self.artifact_store)[0]
        new = self.artifact_store.read_text(record.artifact_id)
        diff = '\n'.join(difflib.unified_diff(
            parent.splitlines(), new.splitlines(),
            fromfile=f'parent {record.target}', tofile='Optimization candidate', lineterm='',
        ))
        return record, diff

    def candidate_action(
        self, active_manifest: Mapping[str, object], candidate_id: str, action: str
    ) -> CandidateRecord:
        record = self.candidate_store.read(candidate_id)
        self._check_candidate_scope(record)
        if action == "review":
            if record.status not in {"proposed", "reviewed", "deferred"}:
                raise ValueError("candidate can no longer be reviewed")
            return self.candidate_store.update(candidate_id, status="reviewed")
        if action in {"defer", "reject"}:
            if record.status not in {"proposed", "reviewed", "deferred"}:
                raise ValueError("candidate can no longer be deferred or rejected")
            return self.candidate_store.update(
                candidate_id, status="deferred" if action == "defer" else "rejected"
            )
        if action != "adopt":
            raise ValueError("candidate action must be review, defer, reject or adopt")
        manifest = self._current_runtime_manifest
        if manifest is None or active_manifest.get("digest") != manifest.digest:
            raise RuntimeError("active runtime changed before candidate adoption")
        if record.status not in {"proposed", "reviewed", "deferred"}:
            raise ValueError("candidate is no longer adoptable")
        if record.parent_manifest_digest != manifest.digest:
            self.candidate_store.update(candidate_id, status="stale")
            raise ValueError("candidate parent version is stale; search again")
        current = self._resolve()
        if current.profile != self._selection.profile or self._configuration.snapshot().changed:
            raise ValueError("configuration changed; resolve it before adopting a candidate")
        target = self._current_targets.get(record.target)
        if target is None or target.snapshot().content_hash != record.parent_target_hash:
            self.candidate_store.update(candidate_id, status="stale")
            raise ValueError("target changed; search again")
        snapshot = target.snapshot()
        if snapshot.binding.kind != record.binding_kind or snapshot.binding.key != record.binding_key:
            raise ValueError("candidate target binding changed")
        target.validate(self.artifact_store.read_text(record.artifact_id))
        if record.binding_kind == "artifact" and record.binding_key in self.data_artifact_bindings and self.data_artifact_bindings[record.binding_key] != record.artifact_id:
            raise ValueError("target is pinned by constructor bindings; update those bindings before adoption")
        try:
            self._configuration.bind_target(record.binding_kind, record.binding_key, record.artifact_id)
            self._configuration.save()
        except BaseException:
            self._configuration.reset()
            raise
        return self.candidate_store.update(candidate_id, status="selected_for_next_session")

    def _check_candidate_scope(self, record):
        scope = (str(self._selection.config_path.resolve()), self._selection.profile.profile_id)
        if record.config_path and (record.config_path, record.profile_id) != scope:
            raise ValueError('candidate belongs to another configuration/profile')

    def _saved_candidate_profile(self, record):
        profile = self._selection.profile
        if record.binding_kind == 'prompt':
            return replace(profile, prompt=record.artifact_id)
        return replace(profile, artifact_bindings={**profile.artifact_bindings, record.binding_key: record.artifact_id})

    def candidate_profile(self, active_manifest, candidate_id):
        """Validate one candidate against the exact active parent and binding."""
        record = self.candidate_store.read(candidate_id)
        self._check_candidate_scope(record)
        if record.status not in {"proposed", "reviewed", "deferred", "selected_for_next_session"}:
            raise ValueError("candidate is no longer adoptable")
        if self._current_runtime_manifest is None or active_manifest.get("digest") != self._current_runtime_manifest.digest or record.parent_manifest_digest != active_manifest.get("digest"):
            raise ValueError("candidate parent version is stale")
        target = self._current_targets.get(record.target)
        if target is None or target.snapshot().content_hash != record.parent_target_hash:
            raise ValueError("candidate target is stale")
        snapshot = target.snapshot()
        if (record.binding_kind, record.binding_key) != (snapshot.binding.kind, snapshot.binding.key):
            raise ValueError("candidate binding differs from target")
        target.validate(self.artifact_store.read_text(record.artifact_id))
        if record.binding_kind == "artifact" and record.binding_key in self.data_artifact_bindings and self.data_artifact_bindings[record.binding_key] != record.artifact_id:
            raise ValueError("target is pinned by constructor bindings; update those bindings before adoption")
        profile = self._active_profile or self._selection.profile
        if record.binding_kind == "prompt":
            profile = replace(profile, prompt=record.artifact_id)
        elif record.binding_kind == "artifact":
            profile = replace(profile, artifact_bindings={**profile.artifact_bindings, record.binding_key: record.artifact_id})
        else:
            raise ValueError("unsupported target binding")
        resolved_profile = self._resolve().profile
        unchanged = resolved_profile == self._selection.profile and not self.configuration.snapshot().changed
        saved_candidate = record.status == "selected_for_next_session" and resolved_profile == self._saved_candidate_profile(record)
        if not (unchanged or saved_candidate):
            raise ValueError("configuration changed before candidate activation")
        return record, profile

    async def prepare_candidate(self, active_manifest, candidate_id):
        """Prepare an isolated candidate without changing saved or active selection."""
        record, profile = self.candidate_profile(active_manifest, candidate_id)
        handle = await self.open(resume=False, session_path=self.new_session_path(), profile_override=profile)
        original_activate = handle.activate_callback
        def activate():
            # Recheck after potentially asynchronous startup, before persistence.
            current_profile = self._resolve().profile
            valid_current = current_profile == self._selection.profile and not self.configuration.snapshot().changed
            valid_saved = record.status == "selected_for_next_session" and current_profile == self._saved_candidate_profile(record)
            if not (valid_current or valid_saved):
                raise ValueError("configuration changed while preparing candidate")
            if not valid_saved:
                # Persist the recoverable intent first. If the process exits
                # after profile save, the next successful startup reconciles it
                # against the actual target hash and manifest.
                self.candidate_store.update(candidate_id, status="selected_for_next_session")
                self.configuration.bind_target(record.binding_kind, record.binding_key, record.artifact_id)
                try:
                    self.configuration.save()
                except BaseException:
                    self.configuration.reset()
                    self.candidate_store.update(candidate_id, status=record.status)
                    raise
                self.reload_configuration()
            self.candidate_store.update(candidate_id, status="adopted", activated_manifest_digest=handle.manifest["digest"])
            original_activate()
        handle.activate_callback = activate
        return handle


def check_session_manifest(
    session: Session,
    runtime: RuntimeAssembly,
    *,
    resume: bool,
    allow_legacy_default_prompt: bool = False,
) -> None:
    entries = session.read_all()
    bindings = [
        entry
        for entry in entries
        if entry.type == "meta"
        and entry.payload.get("kind") == _RUNTIME_MANIFEST_KIND
    ]
    if not resume:
        if entries:
            raise ValueError(
                "session path already contains data; use --resume or a new session path"
            )
        return
    if not bindings:
        raise ValueError("session has no runtime manifest; start a new session")
    stored = bindings[0].payload.get("manifest")
    expected = runtime.manifest.to_dict()
    if isinstance(stored, dict) and stored.get("schema_version") in (3, 4):
        if not allow_legacy_default_prompt or not _known_legacy_default():
            raise ValueError("legacy session prompt identity cannot be verified; start a new session")
        expected = runtime.manifest.legacy_dict(stored["schema_version"])
    if stored != expected or any(
        item.payload.get("manifest") != stored for item in bindings[1:]
    ):
        raise ValueError(
            "resolved runtime differs from this session; start a new session "
            "for configuration changes to take effect"
        )


def _known_legacy_default() -> bool:
    """Do not infer an old session's prompt from a changed builtin definition."""
    return DEFAULT_PROMPT.content_hash == _LEGACY_DEFAULT_PROMPT_HASH


_LEGACY_DEFAULT_PROMPT_HASH = "sha256:dba2d1f5d6975a2fa0d0812defd6562d8efb9df4799332bda2cab6ddd8d25ff1"


def _session_prompt_reference(session: Session) -> str | None:
    for entry in session.read_all():
        if entry.type != "meta" or entry.payload.get("kind") != _RUNTIME_MANIFEST_KIND:
            continue
        manifest = entry.payload.get("manifest")
        if not isinstance(manifest, dict):
            raise ValueError("session runtime manifest is invalid")
        if manifest.get("schema_version") in (3, 4):
            return DEFAULT_PROMPT_ID
        prompt = manifest.get("base_prompt")
        if not isinstance(prompt, dict) or not isinstance(prompt.get("reference"), str):
            raise ValueError("session runtime manifest has no base prompt identity")
        return prompt["reference"]
    return None


def _session_artifact_bindings(session: Session) -> dict[str, str]:
    manifests = [
        entry.payload.get("manifest")
        for entry in session.read_all()
        if entry.type == "meta"
        and entry.payload.get("kind") == _RUNTIME_MANIFEST_KIND
    ]
    if not manifests or not isinstance(manifests[0], dict):
        return {}
    artifacts = manifests[0].get("data_artifacts", ())
    if not isinstance(artifacts, (list, tuple)):
        raise ValueError("session runtime manifest has invalid data_artifacts")
    bindings: dict[str, str] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("session runtime manifest has an invalid data artifact")
        key, artifact_id = artifact.get("key"), artifact.get("id")
        if not isinstance(key, str) or not isinstance(artifact_id, str) or key in bindings:
            raise ValueError("session runtime manifest has an invalid data artifact binding")
        bindings[key] = artifact_id
    return bindings


def record_session_manifest(session: Session, runtime: RuntimeAssembly) -> None:
    if any(
        entry.type == "meta"
        and entry.payload.get("kind") == _RUNTIME_MANIFEST_KIND
        for entry in session.read_all()
    ):
        return
    session.append(
        "meta",
        {
            "kind": _RUNTIME_MANIFEST_KIND,
            "manifest": runtime.manifest.to_dict(),
        },
        sync=True,
    )


def resolve_session_path(
    *,
    cwd: Path,
    session_path: str | None,
    resume: bool,
) -> Path:
    if session_path:
        path = Path(session_path)
        return path if path.is_absolute() else (cwd / path).resolve()

    state_dir = cwd / ".fruitfly"
    if resume:
        candidates = discover_resumable_sessions(cwd)
        if candidates:
            return Path(candidates[0].path)
        legacy = state_dir / "session.jsonl"
        return legacy
    return new_session_path(cwd)


def discover_resumable_sessions(
    cwd: Path,
    *,
    current_path: Path | None = None,
    manifest_digest: str | None = None,
    manifest_digests: set[str] | None = None,
) -> tuple[ResumableSession, ...]:
    """Inspect valid non-empty sessions without leaking transcript content."""

    state_dir = cwd / ".fruitfly"
    paths = list((state_dir / "sessions").glob("*.jsonl"))
    legacy = state_dir / "session.jsonl"
    if legacy.is_file():
        paths.append(legacy)
    current = current_path.resolve() if current_path is not None else None
    candidates: list[ResumableSession] = []
    for path in paths:
        resolved = path.resolve()
        if current is not None and resolved == current:
            continue
        try:
            candidate = _inspect_resumable_session(
                resolved,
                manifest_digest=manifest_digest,
                manifest_digests=manifest_digests,
            )
        except (OSError, SessionCorruptError, TypeError, ValueError):
            continue
        if candidate is not None:
            candidates.append(candidate)
    return tuple(
        sorted(
            candidates,
            key=lambda item: (item.modified_at, item.path),
            reverse=True,
        )
    )


def _inspect_resumable_session(
    path: Path,
    *,
    manifest_digest: str | None,
    manifest_digests: set[str] | None,
) -> ResumableSession | None:
    with Session(path) as session:
        messages = session.messages()
        if not messages:
            return None
        bindings = [
            entry.payload.get("manifest")
            for entry in session.read_all()
            if entry.type == "meta"
            and entry.payload.get("kind") == _RUNTIME_MANIFEST_KIND
        ]
        if not bindings or not isinstance(bindings[0], dict):
            return None
        manifest = bindings[0]
        if any(binding != manifest for binding in bindings[1:]):
            return None
        digest = manifest.get("digest")
        if not isinstance(digest, str) or not digest:
            return None
        if manifest_digests is not None and digest not in manifest_digests:
            return None
        if manifest_digest is not None and digest != manifest_digest:
            return None
        models = manifest.get("models")
        main = models.get("main") if isinstance(models, dict) else None
        model = main.get("model") if isinstance(main, dict) else ""
        profile = manifest.get("profile")
        prompt = manifest.get("base_prompt")
        prompt_label = prompt.get("label", "") if isinstance(prompt, dict) else DEFAULT_PROMPT.label
        prompt_hash = prompt.get("content_hash", "") if isinstance(prompt, dict) else DEFAULT_PROMPT.content_hash
        return ResumableSession(
            path=str(path),
            modified_at=path.stat().st_mtime,
            message_count=len(messages),
            profile=str(profile or ""),
            model=str(model or ""),
            prompt_label=str(prompt_label),
            prompt_hash=str(prompt_hash),
        )


def new_session_path(cwd: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return cwd / ".fruitfly" / "sessions" / (
        f"{timestamp}-{uuid.uuid4().hex[:8]}.jsonl"
    )


async def _close_resources(resources: list[object]) -> None:
    seen: set[int] = set()
    for resource in reversed(resources):
        if id(resource) in seen:
            continue
        seen.add(id(resource))
        close = getattr(resource, "close", None)
        if close is None:
            continue
        try:
            result = close()
            if isawaitable(result):
                await result
        except Exception:
            # Preserve the assembly error; normal RuntimeHandle.close reports
            # cleanup failures when a runtime was successfully opened.
            continue


__all__ = [
    "RunApplicationFactory",
    "check_session_manifest",
    "discover_resumable_sessions",
    "new_session_path",
    "record_session_manifest",
    "resolve_session_path",
]
