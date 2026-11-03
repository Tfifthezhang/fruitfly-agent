"""Built-in mechanism definitions used by the harness composition root."""

from __future__ import annotations

from dataclasses import replace
from fruitfly_agent.runtime_spec.documents import parameter_default
from typing import Any, Mapping

from fruitfly_agent.lab.context_manager.reduction.registration import definitions as reduction_definitions
from fruitfly_agent.lab.context_manager.measurement.registration import install as install_measurement
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
from fruitfly_agent.lab.tools.web.registration import definitions as web_definitions
from fruitfly_agent.lab.context_manager.augmentation.skills.document import definition as skill_document_definition
from fruitfly_agent.lab.context_manager.augmentation.skills.registration import definition as skill_catalog_definition
from fruitfly_agent.lab.improvement.targets.text import TEXT_TARGET_PREFIX
from fruitfly_agent.improvement.contracts.versions import STATE_SNAPSHOTS_COMPONENT
from fruitfly_agent.lab.context_manager.augmentation.information.file_memory.snapshots import FileMemorySnapshots
from fruitfly_agent.lab.improvement.targets.state import WorkspaceTextSnapshots
from fruitfly_agent.improvement.contracts.versions import EXPERIMENT_BLOCKERS_COMPONENT
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget, configuration_surface as prompt_surface
from fruitfly_agent.lab.tools.catalog import prepare_catalog, configuration_surface as tool_catalog_surface
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
from fruitfly_agent.lab.execution_policy import configuration_surface as execution_surface
from .model_roles import ModelRoleRequirement
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
            prepare_targets=_prepare_instruction_components,
            configuration_surfaces=(prompt_surface(), execution_surface(), tool_catalog_surface()),
            artifact_slots=frozenset({'tool-catalog'}),
            component_specs=lambda parameters, enabled: (ComponentSpec('base_prompt'), ComponentSpec('tool-catalog', kind='tool-catalog')),
            implementation_path='fruitfly_agent/lab/improvement/targets/bundle.py',
            documentation_path='fruitfly_agent/lab/improvement/targets/README.md'),
        ssh_definition(),
        mcp_definition(),
        *web_definitions(),
        _definition(
            "local-env",
            optimization_exemption='Execution backend binding; tool and context owners expose optimization surfaces.',
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
            execution_description=lambda parameters, workspace: ExecutionEnvironmentDescription('Local', str(workspace)),
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
            parameters=(ParameterDescriptor('default_timeout_seconds', 'number', 'Command timeout', 'Default seconds per shell command.', parameter_default('fruitfly_agent.lab.tools', 'bash-tool.yaml', 'settings.default_timeout_seconds'), minimum=1, maximum=28800),
                ParameterDescriptor('max_active_commands', 'integer', 'Active commands', 'Runtime-owned managed shell jobs.', parameter_default('fruitfly_agent.lab.tools', 'bash-tool.yaml', 'settings.max_active_commands'), minimum=1, maximum=16),
                ParameterDescriptor('retained_commands', 'integer', 'Command handles', 'Maximum retained command handles.', parameter_default('fruitfly_agent.lab.tools', 'bash-tool.yaml', 'settings.retained_commands'), minimum=16, maximum=256),
                ParameterDescriptor('output_characters', 'integer', 'Poll output', 'Maximum characters per managed poll.', parameter_default('fruitfly_agent.lab.tools', 'bash-tool.yaml', 'settings.output_characters'), minimum=100, maximum=24000)),
            implementation_path='fruitfly_agent/lab/tools/bash.py',
            documentation_path='fruitfly_agent/lab/tools/README.md',
            default=True,
            order=21,
            requires_capabilities=frozenset({"execution-env"}),
            effects=MechanismEffects(tools=("bash",)),
            default_resource=('fruitfly_agent.lab.tools', 'bash-tool.yaml'),
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
            validate_parameters=lambda values: IpythonToolConfig(**values),
            parameter_paths={name: 'instructions.usage' if name == 'usage_instructions' else
                'instructions.query' if name == 'query_instructions' else 'settings.' + name
                for name in IpythonToolConfig.__dataclass_fields__},
            model_role_parameters={'context_query': ModelRoleRequirement('query_model_profile', 'Answer bounded IPython model queries.')},
            input_parameters=('query_model_profile',),
            effects=MechanismEffects(
                uses_provider=True,
                uses_network=True,
                writes_files=True,
                tools=("ipython",),
                cost_notice="IPython execution is local; llm_query may incur Provider cost.",
            ),
            default_resource=('fruitfly_agent.lab.context_manager.externalization', 'ipython-tool.yaml'),
        ),
        skill_catalog_definition(),
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
                ParameterDescriptor("top_k", "integer", "Maximum hits", "Maximum snippets per request.", parameter_default('fruitfly_agent.lab.context_manager.augmentation.information', 'information-context.yaml', 'settings.top_k'), minimum=1),
                ParameterDescriptor("max_chars", "integer", "Context characters", "Maximum injected information characters.", parameter_default('fruitfly_agent.lab.context_manager.augmentation.information', 'information-context.yaml', 'settings.max_chars'), minimum=1),
            ),
            default_resource=('fruitfly_agent.lab.context_manager.augmentation.information', 'information-context.yaml'),
        ),
        _definition(
            "memory-files",
            optimization_exemption='Filesystem source binding; retained editable memory uses an S document owner.',
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
            parameters=(_path_parameter("root", parameter_default('fruitfly_agent.lab.context_manager.augmentation.information.file_memory', 'defaults.yaml', 'root'), "Memory directory"),),
            default_resource=('fruitfly_agent.lab.context_manager.augmentation.information.file_memory', 'defaults.yaml'),
        ),
        _definition(
            "knowledge-files",
            optimization_exemption='Read-only task knowledge source; retained editable knowledge uses an S document owner.',
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
            parameters=(_path_parameter("root", parameter_default('fruitfly_agent.lab.context_manager.augmentation.information.local_knowledge', 'defaults.yaml', 'root'), "Knowledge directory"),),
            default_resource=('fruitfly_agent.lab.context_manager.augmentation.information.local_knowledge', 'defaults.yaml'),
        ),
        _definition(
            "live-http",
            optimization_exemption='External information connector; experiments require a frozen response source.',
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
                ParameterDescriptor("endpoint", "string", "HTTPS endpoint", "HTTPS URL containing one {query} placeholder.", parameter_default('fruitfly_agent.lab.context_manager.augmentation.information.live_http', 'defaults.yaml', 'endpoint')),
                ParameterDescriptor("timeout_seconds", "number", "Timeout", "Maximum seconds for one request.", parameter_default('fruitfly_agent.lab.context_manager.augmentation.information.live_http', 'defaults.yaml', 'timeout_seconds'), minimum=0.1, maximum=30.0),
            ),
            effects=MechanismEffects(uses_network=True, cost_notice="The configured endpoint may have its own charges."),
            default_resource=('fruitfly_agent.lab.context_manager.augmentation.information.live_http', 'defaults.yaml'),
        ),
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
            validate_parameters=lambda values: RlmIpythonConfig(**values),
            implementation_path='fruitfly_agent/lab/context_manager/externalization/adapter.py',
            documentation_path='fruitfly_agent/lab/context_manager/externalization/programmatic_context/README.md',
            requires=frozenset({"ipython-tool"}),
            order=65,
            parameters=(
                ParameterDescriptor(
                    "offload_threshold_chars", "integer", "Offload threshold",
                    "Minimum characters before content is stored as an artifact.",
                    parameter_default('fruitfly_agent.lab.context_manager.externalization', 'rlm-ipython.yaml', 'settings.offload_threshold_chars'),
                    minimum=1, advanced=True,
                ),
                ParameterDescriptor('usage_instructions', 'string', 'Reference guidance',
                    'How to read externalized context references.', RlmIpythonConfig().usage_instructions),
            ),
            effects=MechanismEffects(
                writes_files=True,
            ),
            default_resource=('fruitfly_agent.lab.context_manager.externalization', 'rlm-ipython.yaml'),
            parameter_paths={'offload_threshold_chars': 'settings.offload_threshold_chars',
                             'usage_instructions': 'instructions.usage'},
        ),
        improvement_definition(),
        skill_document_definition(),
    )
    from fruitfly_agent.lab.tools.improvement import expose as tool_surfaces
    from fruitfly_agent.lab.context_manager.augmentation.improvement import expose as augmentation_surfaces
    from fruitfly_agent.lab.context_manager.externalization.improvement import expose as externalization_surfaces
    from .defaults import declared_defaults
    definitions = tuple(declared_defaults(tool_surfaces(augmentation_surfaces(externalization_surfaces(d)))) for d in definitions)
    return LabCatalog(definitions, bootstrap=lambda state, context: (
        install_measurement(state, context).with_component(TEXT_TARGET_PREFIX + "base_prompt", BasePromptTarget(state.config.system_prompt))
        .with_component(TASK_PACK_COMPONENT, TaskPackCatalog(context.workspace, context.task_pack_sources))
    ))


def _prepare_instruction_components(state, context):
    if TEXT_TARGET_PREFIX + 'base_prompt' not in state.components:
        state = state.with_component(TEXT_TARGET_PREFIX + 'base_prompt', BasePromptTarget(state.config.system_prompt))
    state = prepare_catalog(state, context)
    return state


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
    optimization_exemption: str = '',
    artifact_slots: frozenset[str] = frozenset(),
    provides: frozenset[str] = frozenset(),
    requires_capabilities: frozenset[str] = frozenset(),
    selection_group: str | None = None,
    selection_group_label: str | None = None,
    selection_group_allow_disabled: bool = True,
    validate_parameters=None,
    component_specs=None,
    configuration_snapshot=None,
    execution_description=None,
    model_role_parameters=None,
    default_resource=None,
    parameter_paths=None,
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
        implementation_id=implementation_id, visible=visible, optimization_exemption=optimization_exemption,
        artifact_slots=artifact_slots, provides=provides,
        requires_capabilities=requires_capabilities, validate_parameters=validate_parameters,
        component_specs=component_specs,
        configuration_snapshot=configuration_snapshot,
        execution_description=execution_description,
        selection_group=selection_group, selection_group_label=selection_group_label,
        selection_group_allow_disabled=selection_group_allow_disabled,
        implementation_path=implementation_path, documentation_path=documentation_path,
        input_parameters=input_parameters,
        model_role_parameters=model_role_parameters or {}, default_resource=default_resource,
        parameter_paths=parameter_paths or {},
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
        ("max_query_concurrent", "Maximum concurrent model queries"),
        ("max_query_input_chars", "Maximum model query input characters"),
        ("max_query_output_tokens", "Maximum model query output tokens"),
        ("max_query_inline_result_chars", "Maximum inline result characters"),
        ("query_timeout_seconds", "Model query timeout seconds"),
    )
    return (*_integer_parameters(defaults, fields), ParameterDescriptor('query_model_profile', 'string',
        'Query model', 'Model role alias; default inherits executor.', ''),
        ParameterDescriptor('usage_instructions', 'string', 'Workspace guidance',
            'How to use the persistent workspace and its artifacts.', defaults.usage_instructions),
        ParameterDescriptor('query_instructions', 'string', 'Query guidance',
            'Default system instructions for bounded text subproblems.', defaults.query_instructions))


def _install_local_env(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    backend = context.execution_env or LocalEnv(str(context.workspace))
    return replace(
        state,
        config=replace(state.config, env=backend),
    ).with_component(EXECUTION_ENVIRONMENT_COMPONENT,
        ExecutionEnvironmentDescription("Local", backend.cwd))


def _install_read_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    return _append_tool(state, create_read_tool(context.media_writer, resources=context.resources))


def _install_save_media_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    if context.media_reader is None:
        raise ValueError('save-media-tool requires a host media resource reader')
    return _append_tool(state, create_save_media_tool(context.media_reader))


def _install_bash_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    from fruitfly_agent.lab.tools.commands import CommandManager
    manager = context.own(CommandManager(max_active=parameters['max_active_commands'],
        retained_commands=parameters['retained_commands'], output_characters=parameters['output_characters']))
    return _append_tool(state, create_bash_tool(default_timeout_seconds=parameters['default_timeout_seconds'], manager=manager)).with_component(
        'managed-operations', manager.operations)


def _install_edit_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    return _append_tool(state, create_edit_tool())


def _install_write_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    return _append_tool(state, create_write_tool())


def _append_tool(state: AssemblyState, tool) -> AssemblyState:
    return replace(state, config=replace(state.config, tools=(*state.config.tools, tool)))


def _install_information_context(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    hub = InformationHub(top_k=parameters["top_k"], max_chars=parameters["max_chars"])
    transformer = InformationRecallTransformer(
        hub.pipeline,
        query_builder=hub.query_builder,
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
