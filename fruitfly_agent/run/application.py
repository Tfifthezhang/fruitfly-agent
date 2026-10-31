"""Compose explicit Run services and expose the Application runtime factory."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping

from fruitfly_agent.improvement.contracts.optimization import TextProjection
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.interactive import ResumableSession
from fruitfly_agent.interactive.application import RuntimeHandle
from fruitfly_agent.improvement.contracts.versions import STATE_SNAPSHOTS_COMPONENT, EXPERIMENT_BLOCKERS_COMPONENT
from fruitfly_agent.lab.catalog import LabCatalog, builtin_catalog, PermissionPolicy
from fruitfly_agent.lab.base_prompt import DEFAULT_PROMPT_ID
from fruitfly_agent.lab.improvement.api import SearchActivitySource
from fruitfly_agent.lab.improvement.tasks import TASK_PACK_COMPONENT, TaskSnapshotStore
from fruitfly_agent.providers.registry import ProviderRegistry

from .profiles import RunConfigurationController
from .configuration.resolution import HarnessSelection, resolve_harness_selection
from .configuration.model_setup import RunModelSetup
from .configuration.mechanism_setup import RunMechanismSetup
from .configuration.profile import HarnessProfile
from .storage.artifacts import DataArtifactStore
from .storage.candidates import CandidateRecord, CandidateStore
from .storage.improvement_runs import ImprovementRunStore
from .runtime.assembly import build_runtime
from .runtime.manifest import RuntimeManifest
from .runtime.preparation import RuntimePreparer, PreparedRuntime
from .runtime.recovery import (check_session_manifest, discover_resumable_sessions,
    new_session_path, record_session_manifest, resolve_session_path)
from .improvement.candidates import RunCandidates
from .improvement.startup_versions import RunStartupVersions
from .improvement.versions import RunVersions
from .improvement.pipeline import RunComponentJobs
from .storage.experience import ExperienceStore
from .adapters.improvement import RunImprovementService
from .adapters.candidates import RunCandidateService
from .adapters.task_packs import RunTaskPackService
from .adapters.runtime import describe_runtime, describe_execution_environment, describe_tool_services
from fruitfly_agent.interactive.contracts.tool_services import ToolServiceStartPlan, ToolServiceStartupApproval
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
        improvement_bindings=None,
        tool_service_startup_approval: ToolServiceStartupApproval | None = None,
        extensions=None,
    ) -> None:
        self.cwd = cwd.resolve()
        self._base_catalog = catalog or builtin_catalog()
        self._base_improvement_bindings = improvement_bindings
        self.permission_policy = permission_policy
        if extensions is None:
            from .extensions import configured_extensions
            extension_config = Path(config_path).expanduser() if config_path is not None else self.cwd / '.fruitfly/config.yaml'
            if not extension_config.is_absolute():
                extension_config = self.cwd / extension_config
            loaded = configured_extensions(extension_config, profile_id=profile_id)
            extensions = loaded if loaded.registrations else None
        self.extensions = extensions
        self.improvement_bindings = extensions.bindings(improvement_bindings) if extensions is not None else improvement_bindings
        self.tool_service_startup_approval = tool_service_startup_approval
        self.task_pack_sources = tuple(task_pack_sources)
        self._task_snapshots = TaskSnapshotStore(self.cwd)
        self.environment = dict(environment)
        self._requested_config_path = config_path
        self._requested_profile_id = profile_id
        self.catalog = extensions.catalog(catalog or builtin_catalog()) if extensions is not None else (catalog or builtin_catalog())
        self.catalog.require_optimization()
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
        self._active_profile: HarnessProfile | None = None
        self._current_targets: dict[str, TextProjection] = {}
        self._selection = self._resolve()
        self._configuration = RunConfigurationController(
            self._selection,
            self.catalog,
            self.artifact_store,
            read_only=self.read_only_configuration,
            secret_resolver=self.environment.get if self.read_only_configuration else None,
            default_config_path=self.cwd / ".fruitfly/default-config.yaml",
        )
        if not self.read_only_configuration:
            self._configure_setup()

        self._preparer = RuntimePreparer(
            workspace=self.cwd, catalog=self.catalog, environment=self.environment,
            artifacts=self.artifact_store, provider_registry=self.provider_registry,
            pinned_bindings=self.data_artifact_bindings, task_pack_sources=self.task_pack_sources,
            permission_policy=self.permission_policy,
            describe=lambda runtime: describe_runtime(runtime, self.catalog),
            describe_environment=describe_execution_environment,
            describe_services=describe_tool_services,
            approve_start=self._approve_tool_service,
            build=lambda *args, **kwargs: build_runtime(
                *args, **{**kwargs, "provider_registry": self.provider_registry}),
        )
        self._compose_improvement()

    async def _approve_tool_service(self, plan):
        if self.tool_service_startup_approval is None:
            return False
        return await self.tool_service_startup_approval(ToolServiceStartPlan(plan.name, plan.command,
            plan.arguments, plan.working_directory, plan.environment_names))

    @property
    def read_only_configuration(self) -> bool:
        return self._selection.config_path.resolve() == (self.cwd / ".fruitfly/default-config.yaml").resolve()

    def _configure_setup(self):
        self._configuration.model_setup = RunModelSetup(
            config_path=self._configuration.config_path, current_profile=self._configuration.profile,
            stage_profile=self._configuration.stage_profile, workspace=self.cwd, environment=self.environment,
            registry=self.provider_registry,
        )
        self._configuration.mechanism_setup = RunMechanismSetup(
            catalog=self.catalog, current_profile=self._configuration.profile,
            stage_profile=self._configuration.stage_profile, enable=self._configuration.set_mechanism,
            credentials=self._configuration.model_setup.credentials,
        )

    def _compose_improvement(self):
        from fruitfly_agent.lab.catalog import normalize_configuration_binding
        self._experience_store = ExperienceStore(self.cwd / '.fruitfly/improvement/experience.json')
        self._versions = RunVersions(
            workspace=self.cwd, artifacts=self.artifact_store, manifest=self.system_manifest,
            improvement_identity=self.improvement_identity,
            restore_improvement_identity=self.restore_improvement_identity,
            normalize_configuration=lambda key, text: normalize_configuration_binding(key, text, self.catalog),
            state_sources=lambda: (*self._current_components.get(STATE_SNAPSHOTS_COMPONENT, ()), self._experience_store),
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
        from dataclasses import fields
        from fruitfly_agent.lab.improvement.api import WorkflowBindings
        pipeline_bindings = self.improvement_bindings or WorkflowBindings()
        self._component_jobs = RunComponentJobs(
            workspace=self.cwd, artifacts=self.artifact_store, experience=self._experience_store,
            manifest=self.system_manifest, version=self.system_version,
            config=lambda: self._current_runtime_config, targets=lambda: tuple(self._current_targets.values()),
            tasks=self.task_pack_catalog, publish=self.publish_component_candidate,
            **{f.name: getattr(pipeline_bindings, f.name) for f in fields(pipeline_bindings)})
        from fruitfly_agent.lab.improvement.api import EDITOR_CONFIG, ASSESSOR_CONFIG, EDITOR_INSTRUCTIONS, SETTINGS, SYSTEM_SETTINGS
        self._component_jobs.defaults = lambda: self._current_components.get(SETTINGS, {})
        self._component_jobs.editor_configuration = lambda: self._current_components.get(EDITOR_CONFIG, self._current_runtime_config)
        self._component_jobs.assessor_configuration = lambda: self._current_components.get(ASSESSOR_CONFIG, self._current_runtime_config)
        self._component_jobs.editor_instructions = lambda: self._current_components.get(EDITOR_INSTRUCTIONS)
        self._component_jobs.system_settings = lambda: self._current_components.get(SYSTEM_SETTINGS, {})
        self._component_jobs.prepare_materialization = self.prepare_candidate_materialization
        self._improvement_service = RunImprovementService(
            jobs=self._component_jobs, activity=self.improvement_activity, cancel=self.cancel_improvement,
            runs=ImprovementRunStore(self.cwd), scope=self.candidate_scope,
        )
        self._candidate_adapter = RunCandidateService(
            workspace=self.cwd, candidates=self._candidate_service,
            artifacts=self.artifact_store, scope=self.candidate_scope,
            prepare_candidate=lambda manifest, candidate_id: self.prepare_candidate(manifest, candidate_id),
        )

        self._task_pack_service = RunTaskPackService(
            task_catalog=self.task_pack_catalog, selected_target=self.improvement_target_id,
            task_projection=self.task_material_target,
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
            read_only=self.read_only_configuration,
            secret_resolver=self.environment.get if self.read_only_configuration else None,
            default_config_path=self.cwd / ".fruitfly/default-config.yaml",
        )
        if not self.read_only_configuration:
            self._configure_setup()

    def replacement_extensions(self):
        """Build a new host without changing the active host or its resources."""
        from .extensions import load_extensions
        from fruitfly_agent.runtime_spec import load_harness_config
        profile = load_harness_config(self.selection.config_path).select(self.selection.profile.profile_id)
        configured = set(self.selection.profile.extensions)
        extra = tuple(v['source'] for v in self.extensions.identities if v['source'] not in configured) if self.extensions else ()
        extensions = load_extensions((*profile.extensions, *extra), workspace=self.cwd)
        replacement = RunApplicationFactory(cwd=self.cwd, environment=self.environment,
            config_path=str(self.selection.config_path), profile_id=profile.profile_id,
            catalog=self._base_catalog, provider_registry=self.provider_registry,
            data_artifact_bindings=self.data_artifact_bindings, task_pack_sources=self.task_pack_sources,
            permission_policy=self.permission_policy, improvement_bindings=self._base_improvement_bindings,
            tool_service_startup_approval=self.tool_service_startup_approval, extensions=extensions)
        replacement._preparer.sessions = self._preparer.sessions
        return replacement

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
            allow_incomplete=self._allow_incomplete and not (
                self._requested_config_path is not None and
                (self.cwd / self._requested_config_path).resolve() == (self.cwd / ".fruitfly/default-config.yaml").resolve()),
        )

    def improvement_activity(self):
        improver = self._improvement_service.running_improver or self._component_jobs.running_improver
        return improver.progress() if isinstance(improver, SearchActivitySource) else None

    def improvement_identity(self):
        from fruitfly_agent.lab.improvement.api import SETTINGS
        return {**self._component_jobs.identity(),
                'configuration': self._current_components.get(SETTINGS, {})}

    def restore_improvement_identity(self, identity, key, text):
        from fruitfly_agent.lab.catalog import restore_component_settings
        settings = restore_component_settings(identity.get('system_settings', {}), key, text, self.catalog)
        return {**identity, **self._component_jobs.identity(system_settings=settings)}

    def improvement_targets(self):
        return tuple(ImprovementTargetView(c.role, c.component_id, c.label, c.available, c.reason)
                     for c in self._component_jobs.workflow_configuration().components)

    def task_material_target(self, target_id):
        target = self._current_targets.get(target_id)
        return getattr(target, 'task_target_id', target_id)

    def cancel_improvement(self) -> bool:
        improver = self._improvement_service.running_improver or self._component_jobs.running_improver
        return improver.cancel() if improver is not None else False

    def _target(self, active_manifest, *, target_id=None):
        target_id = target_id or self.improvement_target_id()
        try:
            target = self._current_targets[target_id]
            snapshot = target.snapshot()
            if snapshot.target_id != target_id:
                raise ValueError("target identity or text schema mismatch")
            return target
        except KeyError as exc:
            raise ValueError(f"improvement target {target_id!r} is not enabled") from exc

    def improvement_target_id(self):
        return next(iter(self._current_targets))

    def improvement_usage(self):
        return dict(self._component_jobs.observed_usage)

    def task_pack_catalog(self):
        if self._current_runtime_config is None:
            raise RuntimeError("no active runtime")
        source = self._current_components.get(TASK_PACK_COMPONENT)
        if source is None:
            raise RuntimeError("this runtime has no task package catalog")
        return source

    async def open(self, *, resume: bool, session_path: Path | None, profile_override=None) -> RuntimeHandle:
        return await self._preparer.open(
            selection=self.selection, improvement_service=self._improvement_service,
            candidate_service=self._candidate_adapter, task_pack_service=self._task_pack_service,
            activated=self._activated, resume=resume, session_path=session_path,
            profile_override=profile_override,
        )

    async def prepare_configuration(self, *, session_path: Path) -> RuntimeHandle:
        """Prepare the draft through normal assembly; publish only on activation."""
        prepared = self.configuration.prepare_application(self.environment)
        handle = await self._preparer.open(
            selection=prepared.selection, improvement_service=self._improvement_service,
            candidate_service=self._candidate_adapter, task_pack_service=self._task_pack_service,
            activated=self._activated, resume=True, session_path=session_path,
            model_specs=prepared.models, environment=prepared.environment,
        )
        activate = handle.activate_callback

        def commit():
            prepared.commit(activate or (lambda: None))
            self._selection = prepared.selection

        handle.activate_callback = commit
        return handle

    async def _prepare_profile(self, profile):
        return await self.open(resume=False, session_path=self.new_session_path(), profile_override=profile)

    def _activated(self, prepared: PreparedRuntime):
        runtime = prepared.runtime
        self._active_profile = prepared.profile
        self._current_runtime_manifest = runtime.manifest
        self._current_components = runtime.components
        self._current_runtime_config = runtime.config
        from fruitfly_agent.lab.improvement.api import bundle_target
        self._current_targets = dict(prepared.targets)
        if self._current_targets:
            self._current_targets['component-bundle'] = bundle_target(tuple(self._current_targets.values()))
        if not prepared.resumed:
            self._candidate_service.reconcile(runtime.manifest, self._current_targets)

    def publish_component_candidate(self, outcome, baseline, adapters):
        from fruitfly_agent.lab.improvement.api import bundle_text
        if outcome.decision is None or outcome.decision.assurance != 'verified':
            raise ValueError('persistent publication requires independent verification')
        target = self._current_targets['component-bundle']
        text = bundle_text(target, outcome.harness)
        if text == target.snapshot().text:
            return ()
        candidate = self._versions.text_candidate(outcome.plan.parent, target.snapshot(), text)
        record = self.candidate_store.create(text=text, algorithm=outcome.plan.generator_id,
            parent_manifest=self.system_manifest(), cases_digest=outcome.task.material_id,
            direction=outcome.plan.direction, seed_score=None, validation_score=None, metric_calls=len(outcome.records),
            evidence=(('Independent confirmation', 'passed'), ('Version candidate', candidate.candidate_id),
                      ('Changed axes', ', '.join(sorted({c.role for c in candidate.changes}))),
                      ('Component job', '.fruitfly/improvement/jobs/' + outcome.plan.job_id),
                      *((('Verification receipt', outcome.verification),) if outcome.verification else ())),
            snapshot=target.snapshot(), config_path=self.candidate_scope()[0], profile_id=self.candidate_scope()[1],
            task_pack_id=outcome.task.origin.partition(':')[2],
            task_pack_name=outcome.task.origin, task_pack_hash=outcome.task.material_id)
        from .storage.results import save_task_result
        save_task_result(self.cwd, record, text)
        self.compact_candidates()
        return (record,)

    def prepare_candidate_materialization(self, directory):
        from copy import deepcopy
        import json
        from dataclasses import asdict
        from fruitfly_agent.lab.catalog import bind_component_changes, materialize_system
        from fruitfly_agent.run.configuration.resolution import model_catalog_path
        profile = deepcopy(self._active_profile or self.selection.profile)
        model_path = model_catalog_path(profile, self.selection.config_path)
        frozen_models = directory / 'baseline-models.yaml'
        frozen_state = self._versions.snapshots.read(self.system_version().state)
        with frozen_models.open('xb') as stream:
            stream.write(model_path.read_bytes())
        def materialize(candidate, registry, destination):
            bound = bind_component_changes(profile, registry.export(candidate.harness, changed_only=False))
            path = materialize_system(bound, destination / 'config.yaml', catalog=self.catalog,
                artifact_reader=self.artifact_store.read_text, model_source=frozen_models,
                resources=frozen_state.files)
            (destination / 'changes.json').write_text(json.dumps({
                'parent': asdict(candidate.parent), 'candidate_id': candidate.candidate_id,
                'changed_components': candidate.changed_ids,
                'changes': [{'component_id': name, 'before': asdict(candidate.base.component(name)),
                    'after': asdict(candidate.harness.component(name))} for name in candidate.changed_ids],
                'reasons': [asdict(r) for r in candidate.reasons]},
                ensure_ascii=False, indent=2), encoding='utf-8')
            return path
        return materialize

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
        target = self._current_targets.get(record.target)
        if target is None or target.snapshot().role != record.role:
            raise ValueError('candidate target is unavailable')
        target.validate(self.artifact_store.read_text(record.artifact_id))
        expected = self._versions.text_candidate(candidate.parent, target.snapshot(),
                                                  self.artifact_store.read_text(record.artifact_id))
        if candidate != expected:
            raise ValueError("candidate artifact differs from its declared version change")

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
        return await self._component_jobs.improve(active_manifest, direction, preview_token=preview_token)

    def improvement_preview(self, active_manifest: Mapping[str, object], request):
        if active_manifest != self.system_manifest():
            raise ValueError('active runtime changed before preview')
        return self._component_jobs.preview(request)

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

    def verified_candidate(self, record, policy_id):
        self._candidate_service.check_scope(record)
        self.check_candidate_version(record)
        return self._component_jobs.verified_candidate(record, policy_id)


__all__ = ["RunApplicationFactory", "check_session_manifest", "discover_resumable_sessions"]
