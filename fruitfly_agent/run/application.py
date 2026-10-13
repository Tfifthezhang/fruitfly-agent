"""Compose explicit Run services and expose the Application runtime factory."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.interactive import ResumableSession
from fruitfly_agent.interactive.application import RuntimeHandle
from fruitfly_agent.lab.algorithms.targets import TextTarget
from fruitfly_agent.lab.catalog import LabCatalog, builtin_catalog, PermissionPolicy
from fruitfly_agent.lab.base_prompt import DEFAULT_PROMPT_ID
from fruitfly_agent.lab.optimization.text_optimizer import (
    TEXT_OPTIMIZATION_TARGET_COMPONENT, TextOptimizer, SearchActivitySource,
)
from fruitfly_agent.lab.optimization.task_packs import TASK_PACK_COMPONENT, TaskSnapshotStore
from fruitfly_agent.providers.registry import ProviderRegistry

from .profiles import RunConfigurationController
from .configuration.resolution import HarnessSelection, resolve_harness_selection
from .configuration.model_setup import RunModelSetup
from .configuration.profile import HarnessProfile
from .storage.artifacts import DataArtifactStore
from .storage.candidates import CandidateRecord, CandidateStore
from .runtime.assembly import build_runtime
from .runtime.manifest import RuntimeManifest
from .runtime.preparation import RuntimePreparer, PreparedRuntime
from .runtime.recovery import (check_session_manifest, discover_resumable_sessions,
    new_session_path, record_session_manifest, resolve_session_path)
from .improvement.candidates import RunCandidates
from .improvement.search_jobs import RunSearchJobs
from .improvement.startup_versions import RunStartupVersions
from .adapters.optimization import RunOptimizationService
from .adapters.candidates import RunCandidateService
from .adapters.task_packs import RunTaskPackService
from .adapters.runtime import describe_runtime


class RunApplicationFactory:
    """Composition root; each service owns its own business state."""

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
        permission_policy: PermissionPolicy | None = None,
    ) -> None:
        self.cwd = cwd.resolve()
        self.permission_policy = permission_policy
        self.task_pack_sources = tuple(task_pack_sources)
        self._task_snapshots = TaskSnapshotStore(self.cwd)
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
        self._configuration.model_setup = RunModelSetup(
            config_path=self._configuration.config_path, current_profile=self._configuration.profile,
            stage_profile=self._configuration.stage_profile, workspace=self.cwd, environment=self.environment,
        )

        self._preparer = RuntimePreparer(
            workspace=self.cwd, catalog=self.catalog, environment=self.environment,
            artifacts=self.artifact_store, provider_registry=self.provider_registry,
            pinned_bindings=self.data_artifact_bindings, task_pack_sources=self.task_pack_sources,
            permission_policy=self.permission_policy,
            describe=lambda runtime: describe_runtime(runtime, self.catalog),
            build=lambda *args, **kwargs: build_runtime(
                *args, **{**kwargs, "provider_registry": self.provider_registry}),
        )
        self._candidate_service = RunCandidates(
            workspace=self.cwd, store=self.candidate_store, artifacts=self.artifact_store,
            scope=self.candidate_scope, profile=lambda: self.selection.profile,
            resolved_profile=lambda: self._resolve().profile,
            configuration=lambda: self.configuration,
            active_manifest=lambda: self._current_runtime_manifest,
            active_profile=lambda: self._active_profile,
            target=lambda identity: self._current_targets.get(identity),
            pinned_bindings=self.data_artifact_bindings,
            prepare_runtime=self._prepare_profile, reload_configuration=self.reload_configuration,
        )
        self._search_jobs = RunSearchJobs(
            workspace=self.cwd, artifacts=self.artifact_store, candidates=self.candidate_store,
            snapshots=self._task_snapshots, active_manifest=lambda: self._current_runtime_manifest,
            optimizer=self._optimizer, target=self._target, task_catalog=self.task_pack_catalog,
            selected_target=self.optimization_target_id, scope=self.candidate_scope,
            compact=self._candidate_service.compact_candidates,
        )
        self._optimization_service = RunOptimizationService(
            jobs=self._search_jobs, activity=self.optimization_activity, cancel=self.cancel_optimization,
        )
        self._candidate_adapter = RunCandidateService(
            workspace=self.cwd, candidates=self._candidate_service,
            artifacts=self.artifact_store, scope=self.candidate_scope,
            prepare_candidate=lambda manifest, candidate_id: self.prepare_candidate(manifest, candidate_id),
        )

        self._task_pack_service = RunTaskPackService(
            task_catalog=self.task_pack_catalog, selected_target=self.optimization_target_id,
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
        self._configuration.model_setup = RunModelSetup(
            config_path=self._configuration.config_path, current_profile=self._configuration.profile,
            stage_profile=self._configuration.stage_profile, workspace=self.cwd, environment=self.environment,
        )

    def new_session_path(self) -> Path:
        return new_session_path(self.cwd)

    def resumable_sessions(self, *, current_path: Path) -> tuple[ResumableSession, ...]:
        return discover_resumable_sessions(self.cwd, current_path=current_path)

    def _resolve(self) -> HarnessSelection:
        return resolve_harness_selection(
            cwd=self.cwd,
            config_path=self._requested_config_path,
            profile_id=self._requested_profile_id,
            environment=self.environment,
            catalog=self.catalog,
            allow_incomplete=self._allow_incomplete,
        )

    def optimization_activity(self):
        optimizer = self._current_optimizer
        return optimizer.progress() if isinstance(optimizer, SearchActivitySource) else None

    def cancel_optimization(self) -> bool:
        return self._current_optimizer.cancel() if self._current_optimizer is not None else False

    def _target(self, active_manifest, *, target_id=None):
        if target_id is None:
            if self._search_jobs.last_target(active_manifest.get("digest")) is not None:
                target_id = self._search_jobs.last_target(active_manifest.get("digest"))
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
        if target_id is None and self._search_jobs.last_target() is not None:
            target_id = self._search_jobs.last_target()
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

    def _optimizer(self, active_manifest: Mapping[str, object]) -> TextOptimizer:
        manifest = self._current_runtime_manifest
        if manifest is None or active_manifest.get("digest") != manifest.digest:
            raise RuntimeError("active runtime changed; start a new Session")
        if self._current_optimizer is None:
            raise RuntimeError("text optimization is not enabled in the active Session; select it in /config first")
        return self._current_optimizer

    async def open(self, *, resume: bool, session_path: Path | None, profile_override=None) -> RuntimeHandle:
        return await self._preparer.open(
            selection=self.selection, optimization_service=self._optimization_service,
            candidate_service=self._candidate_adapter, task_pack_service=self._task_pack_service,
            activated=self._activated, resume=resume, session_path=session_path,
            profile_override=profile_override,
        )

    async def _prepare_profile(self, profile):
        return await self.open(resume=False, session_path=self.new_session_path(), profile_override=profile)

    def _activated(self, prepared: PreparedRuntime):
        runtime = prepared.runtime
        self._active_profile = prepared.profile
        self._current_runtime_manifest = runtime.manifest
        self._current_components = runtime.components
        self._current_runtime_config = runtime.config
        self._current_optimizer = prepared.optimizer
        self._current_targets = prepared.targets
        self._search_jobs.clear()
        if not prepared.resumed:
            self._candidate_service.reconcile(runtime.manifest, prepared.targets)

    def candidate_scope(self):
        return str(self.selection.config_path.resolve()), self.selection.profile.profile_id

    def startup_versions(self):
        return RunStartupVersions(
            config_path=lambda: self.selection.config_path,
            profile=lambda: self.selection.profile,
            active_profile=lambda: self._active_profile,
            resolved_profile=lambda: self._resolve().profile,
            configuration=lambda: self.configuration,
            resolve_mechanisms=self.catalog.resolve,
            store=self.candidate_store, artifacts=self.artifact_store,
            candidates=self._candidate_service,
            target=lambda identity: self._current_targets.get(identity),
            pinned_bindings=self.data_artifact_bindings,
            prepare_runtime=self._prepare_profile, reload_configuration=self.reload_configuration,
        )

    async def optimize(
        self, active_manifest: Mapping[str, object], direction: str, *, preview_token: str = ""
    ) -> tuple[CandidateRecord, ...]:
        return await self._search_jobs.optimize(active_manifest, direction, preview_token=preview_token)

    def optimization_preview(self, active_manifest: Mapping[str, object], *, pack_id=None, direction=""):
        return self._search_jobs.optimization_preview(active_manifest, pack_id=pack_id, direction=direction)

    def compact_candidates(self):
        return self._candidate_service.compact_candidates()

    def candidates(self) -> tuple[CandidateRecord, ...]:
        return self._candidate_service.candidates()

    def candidate_notice(self) -> tuple[str, ...]:
        return self._candidate_service.candidate_notice()

    def acknowledge_candidate_notice(self, candidate_ids: tuple[str, ...]) -> None:
        return self._candidate_service.acknowledge_candidate_notice(candidate_ids)

    def candidate_detail(self, candidate_id: str) -> tuple[CandidateRecord, str]:
        return self._candidate_service.candidate_detail(candidate_id)

    def candidate_action(
        self, active_manifest: Mapping[str, object], candidate_id: str, action: str
    ) -> CandidateRecord:
        return self._candidate_service.candidate_action(active_manifest, candidate_id, action)

    def _check_candidate_scope(self, record):
        return self._candidate_service.check_scope(record)

    def candidate_profile(self, active_manifest, candidate_id):
        return self._candidate_service.candidate_profile(active_manifest, candidate_id)

    async def prepare_candidate(self, active_manifest, candidate_id):
        return await self._candidate_service.prepare_candidate(active_manifest, candidate_id)


__all__ = ["RunApplicationFactory", "check_session_manifest", "discover_resumable_sessions"]
