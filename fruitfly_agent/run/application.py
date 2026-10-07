"""Concrete application factory for the profile-driven local harness."""

from __future__ import annotations

from dataclasses import replace
import difflib
from inspect import isawaitable
from pathlib import Path
from typing import Any, Mapping

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.session.storage import Session
from fruitfly_agent.interactive import (
    InteractiveMechanism,
    InteractiveSession,
    ResumableSession,
)
from fruitfly_agent.interactive.application import RuntimeHandle
from fruitfly_agent.lab.algorithms.targets import TEXT_TARGET_PREFIX, TextTarget
from fruitfly_agent.lab.catalog import LabCatalog, builtin_catalog
from fruitfly_agent.lab.base_prompt import DEFAULT_PROMPT_ID
from fruitfly_agent.lab.optimization.text_optimizer import TEXT_OPTIMIZER_COMPONENT, TEXT_OPTIMIZATION_TARGET_COMPONENT, TextOptimizer, SearchActivitySource
from fruitfly_agent.lab.optimization.task_packs import TASK_PACK_COMPONENT, TaskSnapshotStore
from fruitfly_agent.providers.registry import ProviderRegistry

from .optimization_service import RunOptimizationService
from .search_jobs import RunSearchJobs

from .assembly import RuntimeManifest, build_runtime, resolve_base_prompt
from .configuration import HarnessProfile
from .artifacts import DataArtifactStore
from .optimization import CandidateRecord, CandidateStore
from .configuration_views import display_section
from .model_setup import RunModelSetup
from .profiles import (
    HarnessSelection,
    RunConfigurationController,
    display_group,
    resolve_harness_selection,
    resolve_profile_models,
)


from .recovery import (
    check_session_manifest,
    discover_resumable_sessions,
    new_session_path,
    record_session_manifest,
    resolve_session_path,
    known_legacy_default,
    session_artifact_bindings,
    session_prompt_reference,
)


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
        self._search_previews: dict[str, tuple] = {}
        self._search_jobs = RunSearchJobs(self)
        self._last_optimization_target: tuple[object, str] | None = None
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
        self._current_runtime_manifest: RuntimeManifest | None = None
        self._current_components: Mapping[str, Any] = {}
        self._current_runtime_config: AgentLoopConfig | None = None
        self._current_optimizer: TextOptimizer | None = None
        self._active_profile: HarnessProfile | None = None
        self._current_targets: dict[str, TextTarget] = {}
        self._selection = self._resolve()
        self._configuration = RunConfigurationController(
            self._selection,
            self.catalog,
            self.artifact_store,
        )
        self._configuration.model_setup = RunModelSetup(self._configuration, self.cwd, self.environment)

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
        self._configuration.model_setup = RunModelSetup(self._configuration, self.cwd, self.environment)

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
        if self._stock_catalog and known_legacy_default() and manifest is not None and manifest.digest == manifest_digest and not any("implementation_id" in item for item in manifest.components):
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
                saved_bindings = session_artifact_bindings(session)
                if saved_bindings:
                    if self.data_artifact_bindings and self.data_artifact_bindings != saved_bindings:
                        raise ValueError(
                            "runtime data artifact bindings differ from this session"
                        )
                    artifact_bindings = saved_bindings
            profile = selection.profile
            if resume:
                saved_prompt = session_prompt_reference(session)
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
                    display_section(self.catalog.get(mechanism_id).descriptor),
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
        return await self._search_jobs.optimize(active_manifest, direction, preview_token=preview_token)

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
        return self._search_jobs.optimization_preview(active_manifest, pack_id=pack_id, direction=direction)

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
        latest: dict[tuple[str, str], CandidateRecord] = {}
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
        if action in {"review", "defer", "reject"}:
            if record.status not in {"proposed", "reviewed", "deferred"}:
                operation = "reviewed" if action == "review" else "deferred or rejected"
                raise ValueError(f"candidate can no longer be {operation}")
            status = {"review": "reviewed", "defer": "deferred", "reject": "rejected"}[action]
            return self.candidate_store.update(candidate_id, status=status)
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
            if original_activate is not None:
                original_activate()
        handle.activate_callback = activate
        return handle


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
