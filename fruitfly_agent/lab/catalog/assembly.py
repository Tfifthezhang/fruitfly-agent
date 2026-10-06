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


@dataclass(frozen=True)
class ProviderBinding:
    provider: Provider
    model: str
    profile: str
    context_window: int | None = None
    max_output_tokens: int | None = None


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace", self.workspace.resolve())
        if self.session_path is not None:
            object.__setattr__(self, "session_path", self.session_path.resolve())
        object.__setattr__(self, "artifact_bindings", dict(self.artifact_bindings))


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

    resolved = catalog.resolve(selections)
    state = AssemblyState(config=base_config)
    if catalog.bootstrap is not None:
        state = catalog.bootstrap(state, context)
        if not isinstance(state, AssemblyState):
            raise TypeError("catalog bootstrap must return AssemblyState")
        _own_state(state, context)
    reduction_stage_id: str | None = None
    for item in resolved:
        descriptor = item.definition.descriptor
        previous_stages = state.context_stages
        previous_reducer = state.reducer
        candidate = item.definition.install(state, context, item.parameters)
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
    for component in state.components.values():
        context.own(component)
    if state.config.env is not None:
        context.own(state.config.env)


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
