"""Prepare new or recovered runtime handles without activating them."""
from __future__ import annotations
from dataclasses import dataclass, replace
from inspect import isawaitable
from pathlib import Path

from fruitfly_agent.improvement.contracts.optimization import TextProjection
from fruitfly_agent.core.extensions.protocols import RecoveryValidator
from fruitfly_agent.interactive import InteractiveSession
from fruitfly_agent.interactive.application import RuntimeHandle
from fruitfly_agent.lab.improvement.targets.text import TEXT_TARGET_PREFIX
from fruitfly_agent.run.configuration.resolution import resolve_profile_models
from fruitfly_agent.run.configuration.profile import HarnessProfile
from fruitfly_agent.run.storage.sessions import SessionLeases
from .assembly import RuntimeAssembly
from .tool_providers import prepare_tool_providers
from .recovery import (new_session_path, check_session_manifest, record_session_manifest,
                       session_manifests)
from .media import load_image


@dataclass(frozen=True)
class PreparedRuntime:
    runtime: RuntimeAssembly
    profile: HarnessProfile
    targets: dict[str, TextProjection]
    resumed: bool


class RuntimePreparer:
    def __init__(self, *, workspace, catalog, environment, artifacts, provider_registry,
                 pinned_bindings, task_pack_sources, permission_policy, build, describe, describe_environment,
                 describe_services=None, approve_start=None):
        self.cwd = workspace
        self.catalog = catalog
        self.environment = environment
        self.artifact_store = artifacts
        self.provider_registry = provider_registry
        self.data_artifact_bindings = dict(pinned_bindings)
        self.task_pack_sources = task_pack_sources
        self.permission_policy = permission_policy
        self.build = build
        self.describe = describe
        self.describe_environment = describe_environment
        self.describe_services = describe_services
        self.approve_start = approve_start
        self.sessions = SessionLeases()

    async def open(
        self,
        *,
        selection,
        improvement_service,
        candidate_service,
        task_pack_service,
        activated,
        resume: bool,
        session_path: Path | None,
        profile_override=None,
        model_specs=None,
        environment=None,
    ) -> RuntimeHandle:
        selection = selection if profile_override is None else replace(selection, profile=profile_override)
        resolve_profile_models(selection.profile, selection.config_path, model_specs=model_specs)
        environment = self.environment if environment is None else environment
        path = session_path or new_session_path(self.cwd)
        lease = self.sessions.acquire(path, resume=resume)
        session = lease.session
        resources: list[object] = []
        try:
            messages = session.messages() if resume else []
            if resume:
                for manifest in session_manifests(session):
                    for service in manifest.get('tool_services', ()):
                        # read_text verifies the content-addressed artifact before any new service starts.
                        self.artifact_store.read_text(service['artifact'])
                        if service['digest'] != service['artifact']:
                            raise ValueError('external tool declaration artifact differs from recorded identity')
            if resume and not messages and not lease.shared:
                raise ValueError("nothing to resume")
            artifact_bindings = {**selection.profile.artifact_bindings, **self.data_artifact_bindings}
            profile = selection.profile
            prepared_tools = await prepare_tool_providers(profile, self.catalog,
                workspace=self.cwd, environment=environment, approve_start=self.approve_start,
                resources=resources, artifacts=self.artifact_store)
            runtime = self.build(
                profile,
                config_path=selection.config_path,
                catalog=self.catalog,
                environment=environment,
                session=session,
                cwd=self.cwd,
                provider_registry=self.provider_registry,
                resource_sink=resources,
                artifact_store=self.artifact_store,
                artifact_bindings=artifact_bindings,
                task_pack_sources=self.task_pack_sources,
                permission_policy=self.permission_policy,
                tool_providers=prepared_tools,
                model_specs=model_specs,
            )
            check_session_manifest(session, runtime, resume=resume)
            saved = session_manifests(session)
            reset_projection = False
            if resume and saved and (
                saved[-1].get("components") != runtime.manifest.to_dict()["components"]
                or saved[-1].get("context_pipeline") != runtime.manifest.context_pipeline
            ):
                # Rebuild projections from canonical facts when context/tool implementations change.
                messages = session.canonical_messages()
                reset_projection = True
            if resume:
                for component in runtime.components.values():
                    if isinstance(component, RecoveryValidator):
                        component.validate_recovery(tuple(messages))
            visible_mechanism_ids, details, tool_categories = self.describe(runtime)
            interaction = InteractiveSession(
                runtime.config,
                context_pipeline=runtime.context_pipeline,
                messages=messages,
                working_directory=self.cwd,
                session_path=path,
                mechanisms=visible_mechanism_ids,
                mechanism_details=details,
                tool_categories=tool_categories,
                execution_environment=self.describe_environment(runtime),
                tool_services=(lambda: self.describe_services(runtime)) if self.describe_services is not None else None,
                load_attachment=lambda path: load_image(path, workspace=self.cwd),
                register_media=runtime.components['media-resources'].put,
                vision=runtime.manifest.models['main']['capabilities']['vision'],
            )
            approvals = runtime.components["authorization"]
            approvals.emit = interaction.emit_frontend_event
            handle = RuntimeHandle(
                session=interaction,
                manifest=runtime.manifest.to_dict(),
                components=runtime.components,
                close_callback=lease.release,
                improvement=improvement_service,
                candidate_activation=candidate_service,
                candidates=candidate_service,
                task_packs=task_pack_service,
                authorization=approvals,
            )
            targets = {key[len(TEXT_TARGET_PREFIX):]: value for key, value in runtime.components.items()
                       if key.startswith(TEXT_TARGET_PREFIX)}
            if any(not isinstance(value, TextProjection) for value in targets.values()):
                raise TypeError("named text targets must implement TextProjection")

            def activate():
                with session.transaction():
                    record_session_manifest(session, runtime, messages=messages if reset_projection else None)
                    activated(PreparedRuntime(runtime, profile, targets, resume))
            handle.activate_callback = activate
            return handle
        except BaseException:
            try:
                await _close_resources(resources)
            finally:
                lease.release()
            raise


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

