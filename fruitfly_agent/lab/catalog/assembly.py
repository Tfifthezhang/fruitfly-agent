"""Deterministic mechanism assembly over an already constructed Core config."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.context import ContextPipeline, ContextReducer, ContextStage
from fruitfly_agent.core.extensions.protocols import Provider, SessionLike

from .catalog import LabCatalog
from .models import MechanismSelection
from .model_roles import ModelRoleRequirement, RoleProvider, role_alias
from fruitfly_agent.core.observation import bind_observation, current_observation


@dataclass(frozen=True)
class ProviderBinding:
    provider: Provider
    model: str
    profile: str
    context_window: int | None = None
    max_output_tokens: int | None = None
    identity: str = ''


ProviderResolver = Callable[[str | None, int | None], ProviderBinding]
ArtifactReader = Callable[[str], str]


@dataclass(frozen=True)
class AssemblyContext:
    workspace: Path
    session: SessionLike
    main_model: str
    provider_resolver: ProviderResolver
    session_path: Path | None = None
    artifact_reader: ArtifactReader | None = None
    artifact_bindings: Mapping[str, str] = field(default_factory=dict)
    resource_sink: list[Any] | None = None
    task_pack_sources: tuple[Any, ...] = ()
    process_environment: Mapping[str, str] | None = None
    execution_owners: Mapping[str, str] = field(default_factory=dict)
    secret_resolver: Callable[[str], str | None] | None = field(default=None, repr=False, compare=False)
    tool_providers: Mapping[str, Any] = field(default_factory=dict)
    component_settings: Mapping[str, Any] = field(default_factory=dict)
    model_roles: Mapping[str, str] = field(default_factory=dict)
    model_metadata: Mapping[str, Any] = field(default_factory=dict)
    media_writer: Callable[[bytes, str, str], str] | None = None
    media_reader: Callable[[str], bytes] | None = None
    resources: Any = None
    execution_env: Any = None
    agent_hooks_from_host: bool = False
    model_requirements: Mapping[str, ModelRoleRequirement] = field(default_factory=dict)
    model_parameters: Mapping[str, Any] = field(default_factory=dict)
    component_id: str = ''
    child_runtime_factory: Any = None
    artifact_store: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace", self.workspace.resolve())
        if self.session_path is not None:
            object.__setattr__(self, "session_path", self.session_path.resolve())
        object.__setattr__(self, "artifact_bindings", dict(self.artifact_bindings))


    def provider_for_role(self, role, max_output_tokens=None):
        if role not in self.model_requirements:
            raise ValueError('undeclared mechanism model role: ' + role)
        alias = role_alias(role, self.model_requirements[role], self.model_parameters, self.model_roles)
        if alias is None:
            raise ValueError('inactive mechanism model role: ' + role)
        with bind_observation(replace(current_observation(), component_id=self.component_id, model_role=role)):
            binding = self.provider_resolver(alias, max_output_tokens)
        return replace(binding, provider=RoleProvider(binding.provider, self.component_id, role))

    def own(self, resource):
        """Register constructor ownership before any later operation can fail.

        Borrowed dependencies must not be registered. Returned components also
        transfer ownership, but own() is required before an installer returns.
        """
        if self.resource_sink is not None and not any(item is resource for item in self.resource_sink):
            self.resource_sink.append(resource)
        return resource


@dataclass(frozen=True)
class AssemblyState:
    config: AgentLoopConfig
    reducer: ContextReducer | None = None
    context_stages: tuple[ContextStage, ...] = ()
    mechanism_ids: tuple[str, ...] = ()
    components: Mapping[str, Any] = field(default_factory=dict)
    data_artifacts: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "mechanism_ids", tuple(self.mechanism_ids))
        object.__setattr__(self, "context_stages", tuple(self.context_stages))
        object.__setattr__(self, "components", dict(self.components))
        object.__setattr__(
            self, "data_artifacts", tuple(dict(item) for item in self.data_artifacts)
        )

    def with_component(self, key: str, value: Any) -> "AssemblyState":
        components = dict(self.components)
        components[key] = value
        return replace(self, components=components)

    def with_context_stage(self, stage: ContextStage) -> "AssemblyState":
        return replace(self, context_stages=(*self.context_stages, stage))

    def with_data_artifact(self, artifact: Mapping[str, Any]) -> "AssemblyState":
        return replace(self, data_artifacts=(*self.data_artifacts, dict(artifact)))

    def with_execution_resource(self, capability, factory):
        """Publish a borrowed trial factory without constructing or starting it."""
        if not isinstance(capability, str) or not capability or not callable(factory):
            raise ValueError('execution resource needs a named factory')
        resources = dict(self.components.get('execution-resources', {}))
        if capability in resources:
            raise ValueError('duplicate execution resource: ' + capability)
        return self.with_component('execution-resources', {**resources, capability: factory})


@dataclass(frozen=True)
class AssemblyResult:
    config: AgentLoopConfig
    context_pipeline: ContextPipeline | None
    mechanism_ids: tuple[str, ...]
    components: Mapping[str, Any]
    data_artifacts: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "mechanism_ids", tuple(self.mechanism_ids))
        object.__setattr__(self, "components", dict(self.components))
        object.__setattr__(
            self, "data_artifacts", tuple(dict(item) for item in self.data_artifacts)
        )


def assemble_lab(
    base_config: AgentLoopConfig,
    *,
    catalog: LabCatalog,
    selections: tuple[MechanismSelection, ...],
    context: AssemblyContext,
) -> AssemblyResult:
    """Validate first, then install every enabled mechanism in stable order."""

    from fruitfly_agent.lab.tools.resources import ResourceRegistry
    resources = context.resources or context.own(ResourceRegistry(scope=str(context.session_path) if context.session_path else None))
    context = replace(context, resources=resources)
    base_config = replace(base_config, readable_resources=resources)
    resolved = catalog.resolve(selections)
    context = replace(context, execution_owners={key: item.definition.descriptor.mechanism_id
        for item in resolved for key in item.definition.execution_fields})
    state = AssemblyState(config=base_config).with_component('readable-resources', resources)
    if catalog.bootstrap is not None:
        state = catalog.bootstrap(state, context)
        if not isinstance(state, AssemblyState):
            raise TypeError("catalog bootstrap must return AssemblyState")
        _own_state(state, context)
    state = _prepare_surfaces(state, context, catalog, resolved)
    reduction_stage_id: str | None = None
    for item in resolved:
        descriptor = item.definition.descriptor
        item_context = replace(context, model_requirements=item.definition.model_role_parameters,
            model_parameters=item.parameters, component_id=descriptor.mechanism_id)
        if item.definition.tool_provider is not None and descriptor.mechanism_id not in context.tool_providers:
            raise ValueError('tool provider requires asynchronous preparation: ' + descriptor.mechanism_id)
        names = item.definition.required_credentials(item.parameters)
        if names:
            secrets = {name: context.secret_resolver(name) if context.secret_resolver is not None else None for name in names}
            missing = [name for name, value in secrets.items() if not value]
            if missing:
                raise ValueError("missing required credentials: " + ", ".join(missing))
            item_context = replace(item_context, secret_resolver=secrets.get)
        previous_stages = state.context_stages
        previous_reducer = state.reducer
        candidate = item.definition.install(state, item_context, item.parameters)
        if not isinstance(candidate, AssemblyState):
            raise TypeError(
                f"mechanism {descriptor.mechanism_id!r} returned "
                f"{type(candidate).__name__}; expected AssemblyState"
            )
        # Ownership transfers on return, including a subsequently rejected state.
        _own_state(candidate, context)
        if candidate.context_stages[: len(previous_stages)] != previous_stages:
            raise ValueError(
                f"mechanism {descriptor.mechanism_id!r} replaced existing context stages"
            )
        added_stages = candidate.context_stages[len(previous_stages) :]
        context_phases = descriptor.context_phases
        prepare_phases = tuple(
            phase for phase in context_phases if phase != "reduction"
        )
        added_prepare = tuple(stage for stage in added_stages if stage.phase != "reduction")
        if prepare_phases:
            if (
                len(added_prepare) != len(prepare_phases)
                or tuple(stage.phase for stage in added_prepare) != prepare_phases
                or any(
                    not _stage_belongs_to(stage.stage_id, descriptor.mechanism_id)
                    for stage in added_prepare
                )
            ):
                raise ValueError(
                    f"mechanism {descriptor.mechanism_id!r} must install exactly "
                    f"its declared context stages: {', '.join(prepare_phases)}"
                )
        elif any(stage.phase in {
            "augmentation",
            "externalization",
        } for stage in added_stages):
            raise ValueError(
                f"mechanism {descriptor.mechanism_id!r} installed undeclared context stages"
            )
        if "reduction" in context_phases:
            changed_reducer = candidate.reducer is not previous_reducer
            added_reduction = len([s for s in added_stages if s.phase == "reduction"]) == 1 and any(
                stage.stage_id == descriptor.mechanism_id
                and stage.phase == "reduction"
                for stage in added_stages
            )
            if changed_reducer and added_reduction:
                raise ValueError(
                    f"mechanism {descriptor.mechanism_id!r} installed reduction twice"
                )
            if not changed_reducer and not added_reduction:
                raise ValueError(
                    f"mechanism {descriptor.mechanism_id!r} did not install its "
                    "declared reduction context stage"
                )
            if changed_reducer:
                reduction_stage_id = descriptor.mechanism_id
        elif any(stage.phase == "reduction" for stage in added_stages):
            raise ValueError(
                f"mechanism {descriptor.mechanism_id!r} installed an undeclared reduction"
            )
        if (
            "reduction" not in context_phases
            and candidate.reducer is not previous_reducer
        ):
            raise ValueError(
                f"mechanism {descriptor.mechanism_id!r} installed an undeclared reduction"
            )
        state = replace(
            candidate,
            mechanism_ids=(*candidate.mechanism_ids, descriptor.mechanism_id),
        )
    # Object adapters see the complete tool set, independently of search enablement.
    # They may consume declared artifacts but cannot start model work.
    state = _prepare_object_targets(state, context, catalog)
    from fruitfly_agent.lab.tools.contracts import contract_fingerprints
    if state.config.tools:
        state = state.with_component('tool-contracts', contract_fingerprints(state.config.tools))
    stages = state.context_stages
    if state.reducer is not None:
        if reduction_stage_id is None:
            raise ValueError("assembled reducer has no declared reduction mechanism")
        stages = (
            *stages,
            ContextStage(
                reduction_stage_id,
                "reduction",
                state.reducer,
                order=1_000,
            ),
        )
    context_pipeline = ContextPipeline(stages) if stages else None
    components = dict(state.components)
    if context_pipeline is not None:
        components["context-pipeline"] = context_pipeline
    return AssemblyResult(
        config=state.config,
        context_pipeline=context_pipeline,
        mechanism_ids=state.mechanism_ids,
        components=components,
        data_artifacts=state.data_artifacts,
    )


def _own_state(state: AssemblyState, context: AssemblyContext) -> None:
    components = (*state.components.values(), *((state.config.env,) if state.config.env is not None else ()))
    # Transfer all ownership before rejecting a malformed component.
    for component in components:
        context.own(component)
    for component in components:
        for method in ('start', 'close', 'validate_recovery'):
            callback = getattr(component, method, None)
            if callback is not None and not callable(callback):
                raise TypeError(f'component {method} must be callable')


def _prepare_object_targets(state, context, catalog):
    for definition in catalog.definitions():
        if definition.prepare_targets is not None:
            state = definition.prepare_targets(state, context)
            if not isinstance(state, AssemblyState):
                raise TypeError('object target preparation must return AssemblyState')
            _own_state(state, context)
    return state


def _prepare_surfaces(state, context, catalog, resolved):
    """Construct active owner targets from the same offline surface declarations."""
    from .defaults import read_default
    from fruitfly_agent.improvement.contracts.optimization import RetainedDocuments
    from fruitfly_agent.improvement.contracts.text import TEXT_TARGET_PREFIX
    from fruitfly_agent.improvement.contracts.versions import STATE_SNAPSHOTS_COMPONENT
    enabled = {item.definition.descriptor.mechanism_id: item for item in resolved}
    for definition in catalog.definitions():
        active = enabled.get(definition.descriptor.mechanism_id)
        for surface in definition.configuration_surfaces:
            if surface.target_factory is None or (active is None and not surface.standalone):
                continue
            owner_context = replace(context, model_parameters=active.parameters if active else {},
                model_requirements=definition.model_role_parameters,
                component_id=definition.descriptor.mechanism_id)
            parameters = context.component_settings.get(surface.key)
            if parameters is None:
                document, _ = read_default(catalog, surface.id)
                parameters = dict(document.parameters)
            reference = context.artifact_bindings.get(surface.id)
            if reference:
                raw = context.artifact_reader(reference)
                parameters = surface.restore(parameters, raw)
                state = state.with_data_artifact({'key': surface.id, 'id': reference, 'role': surface.role,
                    'media_type': 'application/json', 'size_bytes': len(raw.encode('utf-8'))})
            target = surface.target_factory(state, owner_context, surface.normalize(parameters))
            if target.optimization != surface.optimization or target.snapshot().role != surface.role:
                raise ValueError('surface target differs from its declaration: ' + surface.id)
            state = state.with_component(TEXT_TARGET_PREFIX + surface.id, target)
            if isinstance(target, RetainedDocuments):
                state = state.with_component(STATE_SNAPSHOTS_COMPONENT,
                    (*state.components.get(STATE_SNAPSHOTS_COMPONENT, ()), target))
            _own_state(state, context)
    return state


def require_workspace_path(workspace: Path, value: str, *, name: str) -> Path:
    """Resolve a mechanism path while preventing accidental workspace escape."""

    path = Path(value)
    candidate = path.resolve() if path.is_absolute() else (workspace / path).resolve()
    try:
        candidate.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ValueError(f"{name} must stay inside the workspace") from exc
    return candidate


def _stage_belongs_to(stage_id: str, mechanism_id: str) -> bool:
    return stage_id == mechanism_id or stage_id.startswith(f"{mechanism_id}.")


__all__ = [
    "ProviderBinding",
    "ProviderResolver",
    "ArtifactReader",
    "AssemblyContext",
    "AssemblyState",
    "AssemblyResult",
    "assemble_lab",
    "require_workspace_path",
]
