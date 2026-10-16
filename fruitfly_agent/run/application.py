"""Compose explicit Run services and expose the Application runtime factory."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.interactive import ResumableSession
from fruitfly_agent.interactive.application import RuntimeHandle
from fruitfly_agent.lab.algorithms.targets import TextTarget, STATE_SNAPSHOTS_COMPONENT, EXPERIMENT_BLOCKERS_COMPONENT
from fruitfly_agent.lab.catalog import LabCatalog, builtin_catalog, PermissionPolicy
from fruitfly_agent.lab.base_prompt import DEFAULT_PROMPT_ID
from fruitfly_agent.lab.improvement.api import (
    TEXT_IMPROVEMENT_TARGET_COMPONENT, TextImprover, SearchActivitySource,
)
from fruitfly_agent.lab.improvement.tasks import TASK_PACK_COMPONENT, TaskSnapshotStore
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
from .improvement.versions import RunVersions
from .improvement.experiments import RunExperiments
from .configuration.profile import HarnessConfig, save_harness_config
from .configuration.resolution import model_catalog_path
from fruitfly_agent.providers.registry import load_model_specs
from .adapters.improvement import RunImprovementService
from .adapters.candidates import RunCandidateService
from .adapters.task_packs import RunTaskPackService
from .adapters.runtime import describe_runtime
from fruitfly_agent.interactive.contracts.improvement import ImprovementTargetView


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
        if (self.cwd / '.fruitfly' / 'optimization').exists():
            raise ValueError('legacy improvement data requires explicit migration: python -m fruitfly_agent.run.migrate_improvement --apply')
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
        candidate_root = (self.cwd / ".fruitfly" / "improvement" / "candidates").resolve()
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
        self._current_improver: TextImprover | None = None
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
        self._versions = RunVersions(
            workspace=self.cwd, artifacts=self.artifact_store, manifest=self.system_manifest,
            improvement_identity=self.improvement_identity,
            state_sources=lambda: self._current_components.get(STATE_SNAPSHOTS_COMPONENT, ()),
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
            version_guard=self.check_candidate_version,
            activation_guard=self.check_candidate_runtime,
        )
        self._search_jobs = RunSearchJobs(
            workspace=self.cwd, artifacts=self.artifact_store, candidates=self.candidate_store,
            snapshots=self._task_snapshots, active_manifest=lambda: self._current_runtime_manifest,
            improver=self._improver, target=self._target, task_catalog=self.task_pack_catalog,
            selected_target=self.improvement_target_id, scope=self.candidate_scope,
            compact=self._candidate_service.compact_candidates,
            freeze_version=self.system_version, candidate_version=self._versions.text_candidate,
            select_method=self.select_improvement_method,
            remember_method=lambda host: self._current_components['improvement-methods'].remember(host),
            release_method=lambda host: self._current_components['improvement-methods'].release(host),
        )
        self._improvement_service = RunImprovementService(
            jobs=self._search_jobs, activity=self.improvement_activity, cancel=self.cancel_improvement,
            targets=self.improvement_targets, methods=self.improvement_methods,
        )
        self._experiments = RunExperiments(
            workspace=self.cwd, artifacts=self.artifact_store, versions=self._versions,
            manifest=self.system_manifest, improver=lambda: self._current_improver,
            target=lambda: self._target(self.system_manifest(), target_id=getattr(self._current_improver, "experiment_target_id")()),
            scope=self.candidate_scope, freeze_runtime=self.freeze_experiment_runtime,
            candidates=self.candidate_store, compact=self._candidate_service.compact_candidates,
        )
        self._candidate_adapter = RunCandidateService(
            workspace=self.cwd, candidates=self._candidate_service,
            artifacts=self.artifact_store, scope=self.candidate_scope,
            prepare_candidate=lambda manifest, candidate_id: self.prepare_candidate(manifest, candidate_id),
        )

        self._task_pack_service = RunTaskPackService(
            task_catalog=self.task_pack_catalog, selected_target=self.improvement_target_id,
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

    def improvement_activity(self):
        improver = (self._search_jobs.running_improver
                    or self._improvement_service.running_improver or self._current_improver)
        return improver.progress() if isinstance(improver, SearchActivitySource) else None

    def improvement_identity(self):
        identity = getattr(self._current_improver, 'improvement_identity', None)
        if callable(identity):
            return identity()
        return {'mechanisms': [c for c in self.system_manifest()['components']
            if any(x.get('layer') == 'improvement' for x in c.get('contributions', ()))]}

    def improvement_methods(self, role, target_id):
        methods = self._current_components.get('improvement-methods')
        return methods.options(role, target_id) if methods is not None else ()

    def select_improvement_method(self, **selection):
        methods = self._current_components.get('improvement-methods')
        if methods is None:
            raise ValueError('this runtime has no improvement method bindings')
        return methods.select(**selection)

    def improvement_targets(self):
        views = []
        for identity, target in self._current_targets.items():
            snapshot = target.snapshot()
            methods = self.improvement_methods(snapshot.role, identity)
            available = any(method.available for method in methods)
            reason = '' if available else '; '.join(dict.fromkeys(method.reason for method in methods if method.reason))
            views.append(ImprovementTargetView(snapshot.role, identity, identity, available,
                reason or ('' if available else 'No executable method, comparison and adoption adapter are registered.')))
        return tuple(views)

    def cancel_improvement(self) -> bool:
        improver = (self._search_jobs.running_improver
                    or self._improvement_service.running_improver or self._current_improver)
        return improver.cancel() if improver is not None else False

    def _target(self, active_manifest, *, target_id=None):
        if target_id is None:
            if self._search_jobs.last_target(active_manifest.get("digest")) is not None:
                target_id = self._search_jobs.last_target(active_manifest.get("digest"))
            else:
                target_id = self._improver(active_manifest).preview().target_id
        try:
            target = self._current_targets[target_id]
            snapshot = target.snapshot()
            if snapshot.target_id != target_id:
                raise ValueError("target identity or text schema mismatch")
            return target
        except KeyError as exc:
            raise ValueError(f"improvement target {target_id!r} is not enabled") from exc

    def improvement_target_id(self):
        target_id = self._current_components.get(TEXT_IMPROVEMENT_TARGET_COMPONENT)
        if target_id is None and self._search_jobs.last_target() is not None:
            target_id = self._search_jobs.last_target()
        if target_id is None and self._current_improver is not None:
            identify = getattr(self._current_improver, 'experiment_target_id', None)
            target_id = identify() if callable(identify) else self._current_improver.preview().target_id
        return target_id or next(iter(self._current_targets))

    def task_pack_catalog(self):
        if self._current_runtime_config is None:
            raise RuntimeError("no active runtime")
        source = self._current_components.get(TASK_PACK_COMPONENT)
        if source is None:
            raise RuntimeError("this runtime has no task package catalog")
        return source

    def _improver(self, active_manifest: Mapping[str, object]) -> TextImprover:
        manifest = self._current_runtime_manifest
        if manifest is None or active_manifest.get("digest") != manifest.digest:
            raise RuntimeError("active runtime changed; start a new Session")
        if self._current_improver is None:
            raise RuntimeError("no executable improvement host is registered in this Session")
        return self._current_improver

    async def open(self, *, resume: bool, session_path: Path | None, profile_override=None) -> RuntimeHandle:
        return await self._preparer.open(
            selection=self.selection, improvement_service=self._improvement_service,
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
        self._current_improver = prepared.improver
        self._current_targets = prepared.targets
        self._search_jobs.clear()
        if not prepared.resumed:
            self._candidate_service.reconcile(runtime.manifest, prepared.targets)

    def candidate_scope(self):
        return str(self.selection.config_path.resolve()), self.selection.profile.profile_id

    def system_manifest(self):
        if self._current_runtime_manifest is None:
            raise RuntimeError("no active runtime")
        return self._current_runtime_manifest.to_dict()

    def system_version(self):
        blockers = self._current_components.get(EXPERIMENT_BLOCKERS_COMPONENT, ())
        if blockers:
            raise ValueError("runtime dependencies cannot be frozen: " + "; ".join(blockers))
        return self._versions.freeze()

    def check_candidate_version(self, record):
        reference = dict(record.evidence).get("Version candidate")
        if reference is None:
            return
        candidate = self._versions.versions.read_candidate(reference)
        if candidate.parent != self.system_version():
            self.candidate_store.update(record.candidate_id, status="stale")
            raise ValueError("candidate parent H/I/S changed; create a new experiment")
        if (len(candidate.changes) != 1 or candidate.changes[0].after != record.artifact_id
                or (candidate.changes[0].role, candidate.changes[0].target_id) != (record.role, record.target)):
            raise ValueError("candidate artifact differs from its declared version change")

    @property
    def benchmark_improvement_available(self):
        methods = self._current_components.get('improvement-methods')
        return methods.experiment_available() if methods is not None else self._experiments.available

    def benchmark_task_preview(self, selection, executor, direction=""):
        self.system_version()
        selection = dict(selection)
        method_id, target_id = selection.pop('method_id', None), selection.pop('target_id', None)
        parameters = selection.pop('parameters', None)
        host = self._experiments
        method = self.select_improvement_method(method_id=method_id, target_id=target_id,
            parameters=parameters, experiment=True)
        host = self._experiments.bind(method, self._target(self.system_manifest(), target_id=method.experiment_target_id()))
        methods = self._current_components['improvement-methods']
        try:
            return self._improvement_service.register_benchmark(host, selection, executor, direction,
                remember=lambda: methods.remember(method), release=lambda: methods.release(method))
        except BaseException:
            methods.release(method)
            raise

    def check_candidate_runtime(self, record, manifest):
        reference = dict(record.evidence).get("Version candidate")
        if reference and dict(record.evidence).get('Experiment'):
            import json
            path = self.cwd / dict(record.evidence)["Experiment"]
            if (not path.resolve().is_relative_to(self.cwd)
                    or any(p.is_symlink() for p in (path, *path.parents))):
                raise ValueError("candidate experiment must remain in its owned workspace")
            experiment = json.loads(path.read_text(encoding="utf-8"))
            if manifest["models"] != experiment["models"] or manifest.get("permissions") != experiment["permissions"]:
                raise ValueError("prepared runtime model or permission conditions changed from the experiment")
        if reference:
            candidate = self._versions.versions.read_candidate(reference)
            if self._versions.freeze(manifest=manifest) != candidate.version:
                raise ValueError("prepared runtime differs from the verified candidate H/I/S")

    def freeze_experiment_runtime(self, root):
        from dataclasses import replace
        profile = self._active_profile or self.selection.profile
        catalog = model_catalog_path(profile, self.selection.config_path)
        load_model_specs(catalog)
        runtime = root / "runtime"
        runtime.mkdir()
        models = runtime / "models.yaml"
        models.write_bytes(catalog.read_bytes())
        profile = replace(profile, model_catalog=str(models),
            artifact_bindings={**profile.artifact_bindings, **self.data_artifact_bindings})
        config = runtime / "config.yaml"
        save_harness_config(config, HarnessConfig(profile.profile_id, {profile.profile_id: profile}))
        return {"config_path": str(config), "profile": profile.profile_id, "working_directory": str(self.cwd)}

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

    async def improve(
        self, active_manifest: Mapping[str, object], direction: str, *, preview_token: str = ""
    ) -> tuple[CandidateRecord, ...]:
        return await self._search_jobs.improve(active_manifest, direction, preview_token=preview_token)

    def improvement_preview(self, active_manifest: Mapping[str, object], *, pack_id=None, direction="", **selection):
        return self._search_jobs.improvement_preview(active_manifest, pack_id=pack_id, direction=direction, **selection)

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
