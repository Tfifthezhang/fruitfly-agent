"""Built-in mechanism definitions used by the harness composition root."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from fruitfly_agent.lab.context_manager.reduction import (
    SummarizingCompactor, SummarizingCompactorConfig,
)
from fruitfly_agent.core.context import ContextStage
from fruitfly_agent.lab.environment import LocalEnv
from fruitfly_agent.lab.context_manager.augmentation.information.adapter import (
    InformationRecallTransformer,
)
from fruitfly_agent.lab.context_manager.augmentation.information import (
    InformationHub,
    create_local_knowledge_space,
    create_live_http_space,
    create_file_memory_space,
)
from fruitfly_agent.lab.context_manager.externalization.adapter import (
    IpythonToolConfig,
    RlmIpythonConfig,
    install_ipython_tool,
    install_rlm_ipython,
)
from fruitfly_agent.lab.optimization.host import HostedTextOptimizer
from fruitfly_agent.lab.optimization.task_packs import TaskPackCatalog, TASK_PACK_COMPONENT
from fruitfly_agent.lab.optimization.opro import OproOptimizer
from fruitfly_agent.lab.optimization.text_optimizer import TEXT_OPTIMIZER_COMPONENT, TEXT_OPTIMIZATION_TARGET_COMPONENT
from fruitfly_agent.lab.context_manager.augmentation.skills import (
    SkillCatalogTransformer, load_skills, render_skills_xml,
)
from fruitfly_agent.lab.context_manager.augmentation.skills.target import SKILL_CATALOG_GUIDANCE_KEY, SkillGuidanceTarget
from fruitfly_agent.lab.algorithms.targets import TEXT_TARGET_PREFIX
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.tools import (
    create_bash_tool,
    create_edit_tool,
    create_read_tool,
    create_write_tool,
)

from .assembly import AssemblyContext, AssemblyState, require_workspace_path
from .catalog import LabCatalog
from .models import (
    MechanismDefinition,
    MechanismContribution,
    MechanismDescriptor,
    MechanismEffects,
    ParameterDescriptor,
)


def builtin_catalog() -> LabCatalog:
    """Return a fresh explicit catalog; callers may inject more definitions."""

    definitions = (
        _definition(
            "local-env",
            layer="capability",
            family="environment",
            label="Local environment",
            description="Use the workspace filesystem and local shell.",
            install=_install_local_env,
            default=True,
            order=10,
            exclusive_group="environment",
            provides=frozenset({"execution-env"}),
        ),
        _definition(
            "read-tool",
            layer="capability",
            family="tools",
            label="Read files",
            description="Read text or image files from the selected environment.",
            install=_install_read_tool,
            default=True,
            order=20,
            requires_capabilities=frozenset({"execution-env"}),
            effects=MechanismEffects(tools=("read",)),
        ),
        _definition(
            "bash-tool",
            layer="capability",
            family="tools",
            label="Run shell commands",
            description="Execute shell commands in the selected environment.",
            install=_install_bash_tool,
            default=True,
            order=21,
            requires_capabilities=frozenset({"execution-env"}),
            effects=MechanismEffects(tools=("bash",)),
        ),
        _definition(
            "edit-tool",
            layer="capability",
            family="tools",
            label="Edit files",
            description="Apply precise replacements to existing text files.",
            install=_install_edit_tool,
            default=True,
            order=22,
            requires_capabilities=frozenset({"execution-env"}),
            effects=MechanismEffects(tools=("edit",)),
        ),
        _definition(
            "write-tool",
            layer="capability",
            family="tools",
            label="Write files",
            description="Create or replace files in the selected environment.",
            install=_install_write_tool,
            default=True,
            order=23,
            requires_capabilities=frozenset({"execution-env"}),
            effects=MechanismEffects(tools=("write",)),
        ),
        _definition(
            "ipython-tool",
            layer="capability",
            family="tools",
            label="Persistent IPython",
            description="Run Python in a persistent Session workspace with artifacts and bounded model queries.",
            install=install_ipython_tool,
            order=24,
            parameters=_ipython_tool_parameters(),
            effects=MechanismEffects(
                uses_provider=True,
                uses_network=True,
                writes_files=True,
                tools=("ipython",),
                cost_notice="IPython execution is local; llm_query may incur Provider cost.",
            ),
        ),
        _definition(
            "skill-catalog",
            artifact_slots=frozenset({SKILL_CATALOG_GUIDANCE_KEY}),
            layer="online",
            family="context",
            context_phase="augmentation",
            label="Skill catalog",
            description="Load visible SKILL.md metadata into the system prompt.",
            install=_install_skill_catalog,
            default=True,
            order=30,
            parameters=(
                _path_parameter("root", ".skills", "Skill root"),
                ParameterDescriptor(
                    "max_chars", "integer", "Maximum catalog characters",
                    "Maximum projected catalog size; oversized XML is omitted, not cut.",
                    16_000, minimum=128, maximum=1_000_000,
                ),
            ),
        ),
        _definition(
            "information-context",
            visible=False,
            layer="online",
            family="context",
            context_phase="augmentation",
            label="Information context",
            description="Select bounded context from independently registered information spaces.",
            install=_install_information_context,
            default=True,
            order=35,
            parameters=(
                ParameterDescriptor("top_k", "integer", "Maximum hits", "Maximum snippets per request.", 5, minimum=1),
                ParameterDescriptor("max_chars", "integer", "Context characters", "Maximum injected information characters.", 4_000, minimum=1),
            ),
        ),
        _definition(
            "memory-files",
            layer="capability",
            family="context",
            label="File memory",
            description="Load a short MEMORY.md index and topic notes; edit with normal file tools.",
            install=_install_memory_files,
            default=True,
            order=40,
            requires=frozenset({"information-context"}),
            parameters=(_path_parameter("root", ".fruitfly/memory", "Memory directory"),),
        ),
        _definition(
            "knowledge-files",
            layer="capability",
            family="context",
            label="Local knowledge",
            description="Search current Markdown and text documents in a local directory.",
            install=_install_knowledge_files,
            order=41,
            requires=frozenset({"information-context"}),
            parameters=(_path_parameter("root", ".fruitfly/knowledge", "Knowledge directory"),),
        ),
        _definition(
            "live-http",
            layer="capability",
            family="context",
            label="Live HTTP information",
            description="Query a configured HTTPS text endpoint for each current question.",
            install=_install_live_http,
            order=42,
            requires=frozenset({"information-context"}),
            parameters=(
                ParameterDescriptor("endpoint", "string", "HTTPS endpoint", "HTTPS URL containing one {query} placeholder.", ""),
                ParameterDescriptor("timeout_seconds", "number", "Timeout", "Maximum seconds for one request.", 5.0, minimum=0.1, maximum=30.0),
            ),
            effects=MechanismEffects(uses_network=True, cost_notice="The configured endpoint may have its own charges."),
        ),
        _definition(
            "compaction",
            layer="online",
            family="context",
            context_phase="reduction",
            label="Summarizing",
            selection_group="reduction",
            selection_group_label="Reduction",
            description="Summarize history with validated, bounded overflow recovery.",
            install=_install_compaction,
            default=True,
            order=60,
            exclusive_group="compaction",
            parameters=_compaction_parameters(),
            implementation_id="summarizing-v2",
            validate_parameters=_validate_compaction_parameters,
            effects=MechanismEffects(
                uses_provider=True, uses_network=True, writes_files=True,
                lifecycle_hooks=("before_compaction",),
                cost_notice="Summarization requests may incur Provider charges.",
            ),
        ),
        _definition(
            "rlm-ipython",
            layer="online",
            family="context",
            context_phase="externalization",
            label="Programmatic Context (RLM)",
            selection_group="externalization",
            selection_group_label="Externalization",
            exclusive_group="externalization",
            description=(
                "Externalize large context for inspection through the IPython tool."
            ),
            install=install_rlm_ipython,
            requires=frozenset({"ipython-tool"}),
            order=65,
            parameters=(
                ParameterDescriptor(
                    "offload_threshold_chars", "integer", "Offload threshold",
                    "Minimum characters before content is stored as an artifact.",
                    RlmIpythonConfig().offload_threshold_chars,
                    minimum=1, advanced=True,
                ),
            ),
            effects=MechanismEffects(
                writes_files=True,
            ),
        ),
        _native_optimizer_definition(OproOptimizer, "OPRO", order=76, roles=("optimizer",),
            extra_parameters=(ParameterDescriptor("batch_size", "integer", "Proposal batch", "Maximum proposals per round.", 2, minimum=1, maximum=5),)),
    )
    return LabCatalog(definitions, bootstrap=lambda state, context: (
        state.with_component(TEXT_TARGET_PREFIX + "base_prompt", BasePromptTarget(state.config.system_prompt))
        .with_component(TASK_PACK_COMPONENT, TaskPackCatalog(context.workspace, context.task_pack_sources))
    ))


def _native_optimizer_definition(strategy_type, label, *, order, roles, extra_parameters=()):
    spec = strategy_type.spec
    def install(state, context, parameters):
        source = state.components[TASK_PACK_COMPONENT].with_legacy(parameters["cases_path"])
        optimizer = HostedTextOptimizer(strategy_type(), state.config, context.workspace, parameters,
            target=state.components.get(TEXT_TARGET_PREFIX + parameters["target"]), label=label,
            role_configs=_search_role_configs(state, context, parameters), task_source=source)
        return (
            state.with_component(TEXT_OPTIMIZER_COMPONENT, context.own(optimizer))
            .with_component(TASK_PACK_COMPONENT, source)
            .with_component(TEXT_OPTIMIZATION_TARGET_COMPONENT, parameters["target"])
        )
    return _definition(spec.algorithm_id, layer="optimization", family="context", label=label,
        description="Search an enabled text target through shared evaluation, history and budgets.",
        install=install, exclusive_group="text-optimizer", selection_group="text-optimizer",
        selection_group_label="Text optimizer", order=order, implementation_id=spec.implementation_id,
        parameters=(
            ParameterDescriptor("target", "string", "Text target", "Enabled named target.", "base_prompt"),
            _path_parameter("cases_path", ".fruitfly/optimization/cases.json", "Default task pack or legacy cases JSON"),
            ParameterDescriptor("rounds", "integer", "Search rounds", "Maximum bounded rounds.", 2, minimum=1, maximum=20),
            ParameterDescriptor("history_limit", "integer", "History view", "Maximum attempts included in generation context.", 5, minimum=1, maximum=20),
            ParameterDescriptor("max_metric_calls", "integer", "Trial budget", "Root trial call limit.", 32, minimum=1, maximum=200),
            ParameterDescriptor("max_model_calls", "integer", "Model budget", "Root Provider attempt limit for all roles and trials.", 64, minimum=1, maximum=300),
            ParameterDescriptor("output_max_tokens", "integer", "Output limit", "Per request output token cap.", 1024, minimum=128, maximum=4096),
            ParameterDescriptor("call_timeout_seconds", "integer", "Call timeout", "Maximum seconds per operation.", 30, minimum=1, maximum=180),
            *(ParameterDescriptor(role + "_profile", "string", role.title() + " model", "Optional model profile; empty uses the active Provider.", "")
              for role in roles),
            *extra_parameters,
        ), effects=MechanismEffects(uses_provider=True, uses_network=True, writes_files=True,
            cost_notice="Explicit search invokes the configured Provider and stores research history; calls may incur charges."))


def _definition(
    mechanism_id: str,
    *,
    layer: str,
    family: str,
    label: str,
    description: str,
    install,
    context_phase: str | None = None,
    parameters: tuple[ParameterDescriptor, ...] = (),
    default: bool = False,
    order: int,
    exclusive_group: str | None = None,
    requires: frozenset[str] = frozenset(),
    conflicts: frozenset[str] = frozenset(),
    activation: str = "new_session",
    effects: MechanismEffects | None = None,
    additional_contributions: tuple[MechanismContribution, ...] = (),
    implementation_id: str | None = None,
    visible: bool = True,
    artifact_slots: frozenset[str] = frozenset(),
    provides: frozenset[str] = frozenset(),
    requires_capabilities: frozenset[str] = frozenset(),
    selection_group: str | None = None,
    selection_group_label: str | None = None,
    selection_group_allow_disabled: bool = True,
    validate_parameters=None,
) -> MechanismDefinition:
    return MechanismDefinition(
        MechanismDescriptor(
            mechanism_id=mechanism_id,
            label=label,
            description=description,
            contributions=(
                MechanismContribution(layer, family, context_phase),
                *additional_contributions,
            ),
            parameters=parameters,
            requires=requires,
            conflicts=conflicts,
            exclusive_group=exclusive_group,
            default_enabled=default,
            install_order=order,
            activation=activation,
            effects=effects or MechanismEffects(),
        ),
        install,
        implementation_id=implementation_id, visible=visible,
        artifact_slots=artifact_slots, provides=provides,
        requires_capabilities=requires_capabilities, validate_parameters=validate_parameters,
        selection_group=selection_group, selection_group_label=selection_group_label,
        selection_group_allow_disabled=selection_group_allow_disabled,
    )


def _path_parameter(name: str, default: str, label: str) -> ParameterDescriptor:
    return ParameterDescriptor(
        name,
        "path",
        label,
        "Workspace-relative path; escaping the workspace is rejected.",
        default,
    )


def _search_role_configs(state, context, parameters):
    roles = {}
    for role in ("optimizer", "meta", "base"):
        profile = parameters.get(role + "_profile")
        if profile:
            binding = context.provider_resolver(profile, parameters["output_max_tokens"])
            roles[role] = replace(state.config, provider=binding.provider, model=binding.model,
                context_window=binding.context_window or state.config.context_window,
                max_tokens=binding.max_output_tokens or state.config.max_tokens)
    return roles


def _integer_parameters(
    source: Any,
    fields: tuple[tuple[str, str], ...],
) -> tuple[ParameterDescriptor, ...]:
    return tuple(
        ParameterDescriptor(
            name,
            "integer",
            label,
            f"Positive integer for {label.casefold()}.",
            getattr(source, name),
            minimum=1,
            advanced=name not in {"consolidate_threshold", "memory_max_items"},
        )
        for name, label in fields
    )


def _ipython_tool_parameters() -> tuple[ParameterDescriptor, ...]:
    defaults = IpythonToolConfig()
    fields = (
        ("max_artifact_bytes", "Maximum artifact bytes"),
        ("max_cell_output_chars", "Maximum cell output characters"),
        ("cell_timeout_seconds", "Cell timeout seconds"),
        ("max_query_calls", "Maximum model query calls"),
        ("max_query_concurrent", "Maximum concurrent model queries"),
        ("max_query_input_chars", "Maximum model query input characters"),
        ("max_query_output_tokens", "Maximum model query output tokens"),
        ("max_query_total_tokens", "Maximum total model query tokens"),
        ("max_query_inline_result_chars", "Maximum inline result characters"),
        ("query_timeout_seconds", "Model query timeout seconds"),
    )
    return _integer_parameters(defaults, fields)


def _compaction_parameters() -> tuple[ParameterDescriptor, ...]:
    from dataclasses import fields
    defaults = SummarizingCompactorConfig()
    descriptors = []
    for field in fields(defaults):
        value = getattr(defaults, field.name)
        kind = "boolean" if isinstance(value, bool) else "integer" if isinstance(value, int) else "number" if isinstance(value, float) else "string"
        descriptors.append(ParameterDescriptor(
            field.name, kind, field.name.replace("_", " ").capitalize(),
            "Summarizing configuration; validated by the algorithm.", value,
            minimum=(0 if field.name == "reserve_tokens" else 1) if kind == "integer" else None,
            advanced=True,
        ))
    return tuple(descriptors)


def _install_local_env(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    return replace(
        state,
        config=replace(state.config, env=LocalEnv(str(context.workspace))),
    )


def _install_read_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    return _append_tool(state, create_read_tool())


def _install_bash_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    return _append_tool(state, create_bash_tool())


def _install_edit_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    return _append_tool(state, create_edit_tool())


def _install_write_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    return _append_tool(state, create_write_tool())


def _append_tool(state: AssemblyState, tool) -> AssemblyState:
    return replace(state, config=replace(state.config, tools=(*state.config.tools, tool)))


def _install_skill_catalog(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    artifact_key = SKILL_CATALOG_GUIDANCE_KEY
    artifact_id = context.artifact_bindings.get(artifact_key)
    if artifact_id is not None:
        if context.artifact_reader is None:
            raise ValueError(
                "skill-catalog artifact binding requires a Run artifact reader"
            )
        guidance = context.artifact_reader(artifact_id)
        block_size = len(
            f"<!-- fruitfly:skill-catalog:start -->\n{guidance}\n"
            "<!-- fruitfly:skill-catalog:end -->"
        )
        if guidance and block_size > parameters["max_chars"]:
            raise ValueError(
                "bound skill-catalog guidance exceeds skill-catalog.max_chars"
            )
        artifact = {
            "key": artifact_key,
            "id": artifact_id,
            "media_type": "text/plain; charset=utf-8",
            "size_bytes": len(guidance.encode("utf-8")),
        }
        state = state.with_data_artifact(artifact)
    else:
        root = require_workspace_path(context.workspace, parameters["root"], name="skill root")
        result = load_skills(root)
        guidance = render_skills_xml(result.skills)
    return state.with_component(TEXT_TARGET_PREFIX + SKILL_CATALOG_GUIDANCE_KEY, SkillGuidanceTarget(guidance, parameters["max_chars"])).with_context_stage(
        ContextStage(
            "skill-catalog",
            "augmentation",
            SkillCatalogTransformer(guidance, max_chars=parameters["max_chars"]),
            order=30,
        )
    )


def _install_information_context(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    hub = InformationHub(top_k=parameters["top_k"], max_chars=parameters["max_chars"])
    transformer = InformationRecallTransformer(
        hub.pipeline,
        guidance=lambda: hub.guidance,
    )
    return state.with_component("information", hub).with_context_stage(
        ContextStage("information-context", "augmentation", transformer, order=35)
    )


def _install_memory_files(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    root = require_workspace_path(context.workspace, parameters["root"], name="memory root")
    hub = state.components["information"]
    hub.register(create_file_memory_space(root))
    hub.add_guidance(
        "File memory is stored as Markdown. Use read, write and edit tools to "
        "inspect or maintain MEMORY.md and topic notes."
    )
    return state


def _install_knowledge_files(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    root = require_workspace_path(context.workspace, parameters["root"], name="knowledge root")
    state.components["information"].register(create_local_knowledge_space(root))
    return state


def _install_live_http(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    state.components["information"].register(
        create_live_http_space(
            parameters["endpoint"],
            timeout=parameters["timeout_seconds"],
        )
    )
    return state


def _install_compaction(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    config = SummarizingCompactorConfig(**parameters)
    binding = context.provider_resolver(None, config.summary_max_tokens)
    reducer = SummarizingCompactor(
        config, binding.provider, summary_model=binding.model,
        summary_context_window=binding.context_window,
        summary_output_limit=binding.max_output_tokens,
    )
    return replace(state, reducer=reducer)


__all__ = ["builtin_catalog"]


def _validate_compaction_parameters(parameters):
    if "profile" in parameters:
        raise ValueError(
            "compaction.profile is unsupported; remove profile and configure "
            "summarization through compaction parameters"
        )
