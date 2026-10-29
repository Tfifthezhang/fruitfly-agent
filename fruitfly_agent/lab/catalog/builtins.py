"""Built-in mechanism definitions used by the harness composition root."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from fruitfly_agent.lab.context_manager.reduction.registration import definitions as reduction_definitions
from fruitfly_agent.lab.context_manager.measurement.registration import definition as measurement_definition
from fruitfly_agent.core.context import ContextStage
from fruitfly_agent.lab.environment import LocalEnv
from fruitfly_agent.lab.environment.description import EXECUTION_ENVIRONMENT_COMPONENT, ExecutionEnvironmentDescription
from fruitfly_agent.lab.environment.ssh.registration import definition as ssh_definition
from fruitfly_agent.lab.mcp.registration import definition as mcp_definition
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
from fruitfly_agent.lab.improvement.tasks import TaskPackCatalog, TASK_PACK_COMPONENT
from fruitfly_agent.lab.improvement.registration import definition as improvement_definition
from fruitfly_agent.lab.workflow import definition as execution_workflow_definition
from fruitfly_agent.lab.tools.web.registration import definitions as web_definitions
from fruitfly_agent.lab.context_manager.augmentation.skills.document import definition as skill_document_definition
from fruitfly_agent.lab.context_manager.augmentation.information.file_memory.learned import definition as learned_memory_definition
from fruitfly_agent.lab.context_manager.augmentation.skills import (
    SkillCatalogTransformer, load_skills, render_skills_xml,
)
from fruitfly_agent.lab.context_manager.augmentation.skills.target import SKILL_CATALOG_GUIDANCE_KEY, SkillGuidanceTarget
from fruitfly_agent.lab.algorithms.targets import TEXT_TARGET_PREFIX
from fruitfly_agent.improvement.contracts.versions import STATE_SNAPSHOTS_COMPONENT
from fruitfly_agent.lab.context_manager.augmentation.information.file_memory.snapshots import FileMemorySnapshots
from fruitfly_agent.lab.algorithms.snapshots import WorkspaceTextSnapshots
from fruitfly_agent.improvement.contracts.versions import EXPERIMENT_BLOCKERS_COMPONENT
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget, configuration_surface as prompt_surface
from fruitfly_agent.lab.tools.guidance import prepare_guidance, guidance_key
from fruitfly_agent.lab.tools import (
    create_bash_tool,
    create_edit_tool,
    create_read_tool,
    create_write_tool,
)
from fruitfly_agent.lab.tools.media import create_save_media_tool

from .assembly import AssemblyContext, AssemblyState, require_workspace_path
from .catalog import LabCatalog
from .components import ComponentSpec
from fruitfly_agent.lab.execution_policy import validate_component_options, configuration_surface as execution_surface
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
        MechanismDefinition(
            MechanismDescriptor('instruction-components', 'Execution instructions',
                'Expose execution instructions as independently bound improvement components.',
                contributions=(MechanismContribution('capability', 'tools'),)),
            lambda state, context, parameters: state, visible=False,
            prepare_targets=_prepare_instruction_components, component_validator=validate_component_options,
            configuration_surfaces=(prompt_surface(), execution_surface()),
            component_specs=lambda parameters, enabled: (ComponentSpec('base_prompt'),
                ComponentSpec('execution-policy', kind='execution-policy', schema='execution-policy-v1',
                    required_capabilities=frozenset({'execution-config'}))),
            implementation_path='fruitfly_agent/lab/algorithms/components.py',
            documentation_path='fruitfly_agent/lab/algorithms/README.md'),
        ssh_definition(),
        mcp_definition(),
        *web_definitions(),
        _definition(
            "local-env",
            layer="capability",
            family="environment",
            label="Local environment",
            description="Use the workspace filesystem and local shell.",
            install=_install_local_env,
            implementation_path='fruitfly_agent/lab/environment/local.py',
            documentation_path='fruitfly_agent/lab/environment/README.md',
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
            implementation_path='fruitfly_agent/lab/tools/read.py',
            documentation_path='fruitfly_agent/lab/tools/README.md',
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
            parameters=(ParameterDescriptor('default_timeout_seconds', 'number', 'Command timeout', 'Default seconds per shell command.', 120, minimum=1, maximum=28800),
                ParameterDescriptor('max_active_commands', 'integer', 'Active commands', 'Runtime-owned managed shell jobs.', 2, minimum=1, maximum=16),
                ParameterDescriptor('retained_commands', 'integer', 'Command handles', 'Maximum retained command handles.', 64, minimum=16, maximum=256),
                ParameterDescriptor('output_characters', 'integer', 'Poll output', 'Maximum characters per managed poll.', 12000, minimum=100, maximum=24000)),
            implementation_path='fruitfly_agent/lab/tools/bash.py',
            documentation_path='fruitfly_agent/lab/tools/README.md',
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
            implementation_path='fruitfly_agent/lab/tools/edit.py',
            documentation_path='fruitfly_agent/lab/tools/README.md',
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
            implementation_path='fruitfly_agent/lab/tools/write.py',
            documentation_path='fruitfly_agent/lab/tools/README.md',
            default=True,
            order=23,
            requires_capabilities=frozenset({"execution-env"}),
            effects=MechanismEffects(tools=("write",)),
        ),
        _definition(
            'save-media-tool', layer='capability', family='tools', label='Save media resources',
            description='Save a session media resource to a local or SSH file.',
            install=_install_save_media_tool,
            implementation_path='fruitfly_agent/lab/tools/media.py',
            documentation_path='fruitfly_agent/lab/tools/README.md',
            default=False, order=24, requires_capabilities=frozenset({'execution-env'}),
            effects=MechanismEffects(tools=('save_media',)),
        ),
        _definition(
            "ipython-tool",
            layer="capability",
            family="tools",
            label="Persistent IPython",
            description="Run Python in a persistent Session workspace with artifacts and bounded model queries.",
            install=install_ipython_tool,
            implementation_path='fruitfly_agent/lab/context_manager/externalization/adapter.py',
            documentation_path='fruitfly_agent/lab/context_manager/externalization/README.md',
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
            configuration_snapshot=lambda parameters, workspace: WorkspaceTextSnapshots(
                require_workspace_path(workspace, parameters['root'], name='Skill root'), workspace).freeze(),
            artifact_slots=frozenset({SKILL_CATALOG_GUIDANCE_KEY}),
            component_specs=lambda parameters, enabled: (ComponentSpec(SKILL_CATALOG_GUIDANCE_KEY),) if enabled else (),
            layer="online",
            family="context",
            context_phase="augmentation",
            label="Skill catalog",
            description="Load visible SKILL.md metadata into the system prompt.",
            install=_install_skill_catalog,
            implementation_path='fruitfly_agent/lab/context_manager/augmentation/skills/adapter.py',
            documentation_path='fruitfly_agent/lab/context_manager/augmentation/skills/README.md',
            input_parameters=('root',),
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
            implementation_path='fruitfly_agent/lab/context_manager/augmentation/information/adapter.py',
            documentation_path='fruitfly_agent/lab/context_manager/augmentation/information/README.md',
            default=True,
            order=35,
            parameters=(
                ParameterDescriptor("top_k", "integer", "Maximum hits", "Maximum snippets per request.", 5, minimum=1),
                ParameterDescriptor("max_chars", "integer", "Context characters", "Maximum injected information characters.", 4_000, minimum=1),
            ),
        ),
        _definition(
            "memory-files",
            configuration_snapshot=lambda parameters, workspace: FileMemorySnapshots(
                require_workspace_path(workspace, parameters['root'], name='memory root'), workspace).freeze(),
            layer="capability",
            family="context",
            label="File memory",
            description="Load a short MEMORY.md index and topic notes; edit with normal file tools.",
            install=_install_memory_files,
            implementation_path='fruitfly_agent/lab/context_manager/augmentation/information/file_memory/__init__.py',
            documentation_path='fruitfly_agent/lab/context_manager/augmentation/information/file_memory/README.md',
            input_parameters=('root',),
            default=True,
            order=40,
            requires=frozenset({"information-context"}),
            parameters=(_path_parameter("root", ".fruitfly/memory", "Memory directory"),),
        ),
        _definition(
            "knowledge-files",
            configuration_snapshot=lambda parameters, workspace: WorkspaceTextSnapshots(
                require_workspace_path(workspace, parameters['root'], name='knowledge root'), workspace).freeze(),
            layer="capability",
            family="context",
            label="Local knowledge",
            description="Search current Markdown and text documents in a local directory.",
            install=_install_knowledge_files,
            implementation_path='fruitfly_agent/lab/context_manager/augmentation/information/local_knowledge/__init__.py',
            documentation_path='fruitfly_agent/lab/context_manager/augmentation/information/local_knowledge/README.md',
            input_parameters=('root',),
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
            implementation_path='fruitfly_agent/lab/context_manager/augmentation/information/live_http/__init__.py',
            documentation_path='fruitfly_agent/lab/context_manager/augmentation/information/live_http/README.md',
            input_parameters=('endpoint',),
            order=42,
            requires=frozenset({"information-context"}),
            parameters=(
                ParameterDescriptor("endpoint", "string", "HTTPS endpoint", "HTTPS URL containing one {query} placeholder.", ""),
                ParameterDescriptor("timeout_seconds", "number", "Timeout", "Maximum seconds for one request.", 5.0, minimum=0.1, maximum=30.0),
            ),
            effects=MechanismEffects(uses_network=True, cost_notice="The configured endpoint may have its own charges."),
        ),
        measurement_definition(),
        *reduction_definitions(),
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
            implementation_path='fruitfly_agent/lab/context_manager/externalization/adapter.py',
            documentation_path='fruitfly_agent/lab/context_manager/externalization/programmatic_context/README.md',
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
        execution_workflow_definition(),
        improvement_definition(),
        skill_document_definition(),
        learned_memory_definition(),
    )
    from fruitfly_agent.lab.tools.guidance import configuration_surface as guidance_surface
    tool_factories = {'read': create_read_tool, 'bash': create_bash_tool,
                      'write': create_write_tool, 'edit': create_edit_tool, 'save_media': create_save_media_tool}
    definitions = tuple(replace(d, artifact_slots=d.artifact_slots | frozenset(
        guidance_key(name) for name in d.descriptor.effects.tools),
        configuration_surfaces=(*d.configuration_surfaces,
            *(guidance_surface(name, tool_factory=tool_factories.get(name))
              for name in d.descriptor.effects.tools))) for d in definitions)
    from fruitfly_agent.lab.improvement.components.parameters import editable_parameters
    parameter_fields = {
        'bash-tool': {'default_timeout_seconds', 'max_active_commands', 'retained_commands', 'output_characters'},
        'ipython-tool': {'max_artifact_bytes', 'max_cell_output_chars', 'cell_timeout_seconds',
            'max_query_calls', 'max_query_concurrent', 'max_query_input_chars', 'max_query_output_tokens',
            'max_query_total_tokens', 'max_query_inline_result_chars', 'query_timeout_seconds'},
        'web-search-tool': {'timeout_seconds', 'max_retries', 'max_response_bytes', 'cache_ttl_seconds',
            'cache_entries', 'backend'},
        'web-fetch-tool': {'timeout_seconds', 'max_retries', 'max_response_bytes', 'cache_ttl_seconds',
            'cache_entries', 'max_redirects', 'backend'},
    }
    definitions = tuple(editable_parameters(d, parameter_fields[d.descriptor.mechanism_id])
        if d.descriptor.mechanism_id in parameter_fields else d for d in definitions)
    return LabCatalog(definitions, bootstrap=lambda state, context: (
        state.with_component(TEXT_TARGET_PREFIX + "base_prompt", BasePromptTarget(state.config.system_prompt))
        .with_component(TASK_PACK_COMPONENT, TaskPackCatalog(context.workspace, context.task_pack_sources))
    ))


def _prepare_instruction_components(state, context):
    from fruitfly_agent.lab.execution_policy import ExecutionPolicyTarget
    if TEXT_TARGET_PREFIX + 'base_prompt' not in state.components:
        state = state.with_component(TEXT_TARGET_PREFIX + 'base_prompt', BasePromptTarget(state.config.system_prompt))
    state = prepare_guidance(state, context)
    return state.with_component(TEXT_TARGET_PREFIX + "execution-policy", ExecutionPolicyTarget(state.config, fixed_fields=context.execution_owners))


def _definition(
    mechanism_id: str,
    *,
    layer: str,
    family: str,
    label: str,
    description: str,
    install,
    implementation_path: str,
    documentation_path: str,
    input_parameters: tuple[str, ...] = (),
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
    component_specs=None,
    configuration_snapshot=None,
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
        component_specs=component_specs,
        configuration_snapshot=configuration_snapshot,
        selection_group=selection_group, selection_group_label=selection_group_label,
        selection_group_allow_disabled=selection_group_allow_disabled,
        implementation_path=implementation_path, documentation_path=documentation_path,
        input_parameters=input_parameters,
    )


def _path_parameter(name: str, default: str, label: str) -> ParameterDescriptor:
    return ParameterDescriptor(
        name,
        "path",
        label,
        "Workspace-relative path; escaping the workspace is rejected.",
        default,
    )


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
            advanced=True,
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


def _install_local_env(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    backend = LocalEnv(str(context.workspace))
    return replace(
        state,
        config=replace(state.config, env=backend),
    ).with_component(EXECUTION_ENVIRONMENT_COMPONENT,
        ExecutionEnvironmentDescription("Local", backend.cwd))


def _install_read_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    return _append_tool(state, create_read_tool(context.media_writer))


def _install_save_media_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    if context.media_reader is None:
        raise ValueError('save-media-tool requires a host media resource reader')
    return _append_tool(state, create_save_media_tool(context.media_reader))


def _install_bash_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    from fruitfly_agent.lab.tools.commands import CommandManager
    manager = context.own(CommandManager(max_active=parameters['max_active_commands'],
        retained_commands=parameters['retained_commands'], output_characters=parameters['output_characters']))
    return _append_tool(state, create_bash_tool(default_timeout_seconds=parameters['default_timeout_seconds'], manager=manager))


def _install_edit_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    return _append_tool(state, create_edit_tool())


def _install_write_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    return _append_tool(state, create_write_tool())


def _append_tool(state: AssemblyState, tool) -> AssemblyState:
    return replace(state, config=replace(state.config, tools=(*state.config.tools, tool)))


def _install_skill_catalog(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    artifact_key = SKILL_CATALOG_GUIDANCE_KEY
    root = require_workspace_path(context.workspace, parameters["root"], name="skill root")
    state = state.with_component(STATE_SNAPSHOTS_COMPONENT,
        (*state.components.get(STATE_SNAPSHOTS_COMPONENT, ()), WorkspaceTextSnapshots(root, context.workspace)))
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
    return state.with_component(STATE_SNAPSHOTS_COMPONENT,
        (*state.components.get(STATE_SNAPSHOTS_COMPONENT, ()), FileMemorySnapshots(root, context.workspace)))


def _install_knowledge_files(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    root = require_workspace_path(context.workspace, parameters["root"], name="knowledge root")
    state.components["information"].register(create_local_knowledge_space(root))
    return state.with_component(STATE_SNAPSHOTS_COMPONENT,
        (*state.components.get(STATE_SNAPSHOTS_COMPONENT, ()), WorkspaceTextSnapshots(root, context.workspace)))


def _install_live_http(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    state.components["information"].register(
        create_live_http_space(
            parameters["endpoint"],
            timeout=parameters["timeout_seconds"],
        )
    )
    return state.with_component(EXPERIMENT_BLOCKERS_COMPONENT,
        (*state.components.get(EXPERIMENT_BLOCKERS_COMPONENT, ()), "Live HTTP context has no frozen response snapshot"))


__all__ = ["builtin_catalog"]
