"""Provider-aware composition of one resolved harness profile."""

from __future__ import annotations

from fruitfly_agent.lab.catalog import PermissionPolicy, apply_permission_policy, ProviderToolAuthorizer
from fruitfly_agent.interactive.interaction.authorization import AuthorizationService
from fruitfly_agent.run.runtime.permissions import default_permission_policy

from dataclasses import asdict, dataclass, replace, field
from pathlib import Path
from typing import Any, Mapping

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.runtime_spec import execution_kwargs, effective_execution
from fruitfly_agent.core.extensions.hooks import HookRegistry
from fruitfly_agent.core.context import ContextPipeline
from fruitfly_agent.core.session.storage import Session
from fruitfly_agent.lab.catalog import (
    AssemblyContext,
    LabCatalog,
    ProviderBinding,
    assemble_lab,
)
from fruitfly_agent.run.configuration import HarnessProfile
from fruitfly_agent.providers.registry import ProviderRegistry, default_registry

from fruitfly_agent.run.configuration.resolution import resolve_profile_models
from fruitfly_agent.run.storage.artifacts import DataArtifactStore
from fruitfly_agent.run.storage.prompts import resolve_base_prompt
from .manifest import RuntimeManifest, digest_manifest as _digest
from fruitfly_agent.lab.catalog import resolve_harness, verify_runtime, configure_profile
from fruitfly_agent.lab.algorithms.targets import TEXT_TARGET_PREFIX


@dataclass(frozen=True)
class RuntimeAssembly:
    config: AgentLoopConfig
    context_pipeline: ContextPipeline | None
    mechanism_ids: tuple[str, ...]
    component_ids: tuple[str, ...]
    components: Mapping[str, Any]
    model_profile: str
    manifest: RuntimeManifest
    tool_providers: Mapping[str, Any] = field(default_factory=dict)


def build_runtime(
    profile: HarnessProfile,
    *,
    config_path: Path,
    catalog: LabCatalog,
    environment: Mapping[str, str],
    session: Session,
    cwd: Path,
    provider_registry: ProviderRegistry | None = None,
    resource_sink: list[Any] | None = None,
    artifact_store: DataArtifactStore | None = None,
    artifact_bindings: Mapping[str, str] | None = None,
    task_pack_sources: tuple = (),
    permission_policy: PermissionPolicy | None = None,
    tool_providers: Mapping[str, Any] | None = None,
) -> RuntimeAssembly:
    """Build a fresh runtime; no result is applied until all installers succeed."""

    profile = configure_profile(profile, catalog)
    prepared = dict(tool_providers or {})
    enabled = catalog.resolve(profile.mechanisms)
    expected_providers = {item.definition.descriptor.mechanism_id for item in enabled if item.definition.tool_provider is not None}
    if set(prepared) - expected_providers:
        raise ValueError('prepared tools have no enabled owner')
    for item in enabled:
        if item.definition.tool_provider is not None and item.definition.descriptor.mechanism_id not in prepared:
            raise ValueError('tool provider requires asynchronous preparation: ' + item.definition.descriptor.mechanism_id)
    store = artifact_store or DataArtifactStore(cwd / ".fruitfly" / "artifacts")
    for reference, text in profile.artifact_contents.items():
        if store.put_text(text).artifact_id != reference:
            raise ValueError('configured artifact content identity differs')
    prompt_text, prompt_identity = resolve_base_prompt(profile.prompt, store)
    models, selected_model_profile, main_spec = resolve_profile_models(
        profile,
        config_path,
    )
    policy = permission_policy or default_permission_policy(cwd, config_path)
    if policy.workspace != cwd.resolve():
        raise ValueError("permission workspace must match runtime workspace")
    approvals = AuthorizationService()
    def audit(data):
        session.append("meta", {"kind": "authorization", **data})
    process_environment = policy.prepare_environment(environment)
    main_spec.require(streaming=True)
    registry = provider_registry or default_registry()
    resolved_model_specs: dict[str, dict[str, Any]] = {}
    providers: dict[str, Any] = {}

    def resolve_provider(
        requested_profile: str | None,
        max_output_tokens: int | None,
    ) -> ProviderBinding:
        profile_id = requested_profile or selected_model_profile
        try:
            spec = models[profile_id]
        except KeyError as exc:
            available = ", ".join(sorted(models)) or "none"
            raise ValueError(
                f"unknown auxiliary model profile {profile_id!r} "
                f"(available: {available})"
            ) from exc
        spec.require(streaming=True)
        if max_output_tokens is not None:
            spec = replace(
                spec,
                max_output_tokens=min(spec.max_output_tokens, max_output_tokens),
            )
        binding_number = len(providers) + 1
        binding_key = "main" if binding_number == 1 else f"auxiliary-{binding_number - 1}"
        resolved_model_specs[binding_key] = {
            "profile": profile_id,
            **asdict(spec),
        }
        provider = registry.create(spec, environment)
        transport_parameters = getattr(provider, "transport_parameters", None)
        if isinstance(transport_parameters, dict):
            resolved_model_specs[binding_key]["transport"] = dict(transport_parameters)
        if resource_sink is not None:
            resource_sink.append(provider)
        providers[f"provider:{binding_key}"] = provider
        return ProviderBinding(
            provider=provider,
            model=spec.model,
            profile=profile_id,
            context_window=spec.context_window,
            max_output_tokens=spec.max_output_tokens,
        )

    main = resolve_provider(selected_model_profile, None)
    base = AgentLoopConfig(
        provider=main.provider,
        model=main.model,
        max_tokens=main_spec.max_output_tokens,
        system_prompt=prompt_text,
        context_window=main_spec.context_window,
        tools=(),
        env=None,
        session=session,
        hooks=HookRegistry(session=session),
        **execution_kwargs(profile.execution),
    )
    bindings = dict(profile.artifact_bindings if artifact_bindings is None else artifact_bindings)
    supported_bindings = {slot for definition in catalog.definitions() for slot in definition.artifact_slots}
    supported_bindings.update('tool-guidance.' + tool.name for provider in prepared.values() for tool in provider.tools)
    unsupported_bindings = sorted(set(bindings) - supported_bindings)
    if unsupported_bindings:
        raise ValueError(
            "unsupported runtime data artifact binding(s): "
            + ", ".join(unsupported_bindings)
        )
    assembled = assemble_lab(
        base,
        catalog=catalog,
        selections=profile.mechanisms,
        context=AssemblyContext(
            workspace=cwd,
            session=session,
            main_model=main.model,
            provider_resolver=resolve_provider,
            session_path=session.path,
            artifact_reader=store.read_text,
            artifact_bindings=bindings,
            resource_sink=resource_sink,
            task_pack_sources=task_pack_sources,
            process_environment=process_environment,
            secret_resolver=environment.get,
            tool_providers=prepared,
            component_settings=profile.component_settings,
            model_roles=profile.model_roles,
            model_metadata={name: {'model': spec.model, 'context_window': spec.context_window,
                                   'max_tokens': spec.max_output_tokens} for name, spec in models.items()},
        ),
    )
    # Apply host policy after all installers, so an installer cannot accidentally omit it.
    secured = apply_permission_policy(assembled.config,
        replace(policy, readonly_paths=(*policy.readonly_paths, session.path.resolve())),
        confirm=approvals.confirm, audit=audit, process_environment=process_environment)
    permission_identity = getattr(secured.tool_authorizer, 'identity', policy.identity)()
    external_policies = {name: rule for provider in prepared.values() for name, rule in provider.policies.items()}
    if external_policies:
        secured = replace(secured, tool_authorizer=ProviderToolAuthorizer(secured.tool_authorizer, external_policies, approvals.confirm, audit=audit))
    assembled = replace(assembled, config=secured,
                        components={**assembled.components, "authorization": approvals})
    main_spec.require(tools=bool(assembled.config.tools), streaming=True)
    resolved = catalog.resolve(profile.mechanisms)
    component_entries = tuple(
        {
            "id": item.definition.descriptor.mechanism_id,
            "contributions": [
                contribution.to_dict()
                for contribution in item.definition.descriptor.contributions
            ],
            "requires": sorted(item.definition.descriptor.requires),
            "activation": item.definition.descriptor.activation,
            **({"requires_capabilities": sorted(item.definition.requires_capabilities)} if item.definition.requires_capabilities else {}),
            "parameters": dict(item.parameters),
            **({"implementation_id": item.definition.implementation_id}
               if item.definition.implementation_id is not None else {}),
        }
        for item in resolved
    )
    data_artifacts = tuple(assembled.data_artifacts)
    bound_keys = {item.get("key") for item in data_artifacts}
    if bound_keys != set(bindings):
        missing = sorted(set(bindings) - bound_keys)
        raise ValueError(
            "runtime data artifact binding(s) were not consumed by an enabled "
            "mechanism: " + ", ".join(missing)
        )
    inventory = verify_runtime(resolve_harness(profile, catalog, tool_providers=prepared), assembled.config,
        tuple(value for key, value in assembled.components.items() if key.startswith(TEXT_TARGET_PREFIX)))
    service_identity = tuple(dict(entry) for provider in prepared.values() for entry in provider.identity)
    manifest_version = 8 if service_identity else 7
    manifest_payload: dict[str, Any] = {
        "schema_version": manifest_version,
        "harness": inventory.to_dict(),
        "profile": profile.profile_id,
        "model_profile": selected_model_profile,
        "models": {
            key: resolved_model_specs[key] for key in sorted(resolved_model_specs)
        },
        "components": component_entries,
        "context_pipeline": (
            assembled.context_pipeline.profile.to_dict()
            if assembled.context_pipeline is not None
            else None
        ),
        "base_prompt": prompt_identity,
        "permissions": permission_identity,
        'execution': effective_execution(assembled.config),
    }
    if data_artifacts:
        manifest_payload["data_artifacts"] = [dict(item) for item in data_artifacts]
    if service_identity:
        manifest_payload['tool_services'] = list(service_identity)
    digest = _digest(manifest_payload)
    manifest = RuntimeManifest(
        schema_version=manifest_version,
        profile=profile.profile_id,
        model_profile=selected_model_profile,
        models=manifest_payload["models"],
        components=component_entries,
        context_pipeline=manifest_payload["context_pipeline"],
        data_artifacts=data_artifacts,
        base_prompt=prompt_identity,
        digest=digest,
        permissions=permission_identity,
        execution=manifest_payload['execution'],
        harness=manifest_payload['harness'],
        tool_services=service_identity,
    )
    optional_ids = tuple(
        item.definition.descriptor.mechanism_id
        for item in resolved
        if any(
            contribution.layer != "capability"
            for contribution in item.definition.descriptor.contributions
        )
    )
    return RuntimeAssembly(
        config=assembled.config,
        context_pipeline=assembled.context_pipeline,
        mechanism_ids=optional_ids,
        component_ids=assembled.mechanism_ids,
        components={**providers, **assembled.components,
                    **{f"owned:{i}": value for i, value in enumerate(resource_sink or ())}},
        model_profile=selected_model_profile,
        manifest=manifest,
        tool_providers=prepared,
    )


__all__ = [
    "resolve_base_prompt",
    "RuntimeManifest",
    "RuntimeAssembly",
    "build_runtime",
]
