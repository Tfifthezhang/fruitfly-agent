"""Owned declarations for native tools; every tool exposes actual instructions."""
from dataclasses import replace
from fruitfly_agent.runtime_spec.documents import parameter_default
from fruitfly_agent.lab.catalog.models import define_mechanism as _definition
from fruitfly_agent.lab.catalog.models import MechanismDefinition, ParameterDescriptor, MechanismEffects
from fruitfly_agent.lab.catalog.classification import OptimizationCoverage
from fruitfly_agent.lab.catalog.assembly import AssemblyState, AssemblyContext, require_workspace_path
from typing import Any, Mapping
from fruitfly_agent.lab.catalog.classification import TOOLS, FILES, IPYTHON
from fruitfly_agent.lab.catalog.model_roles import ModelRoleRequirement
from fruitfly_agent.lab.tools import create_read_tool, create_write_tool, create_edit_tool, create_bash_tool
from fruitfly_agent.lab.tools.methods.ipython.runtime import IpythonToolConfig, install_ipython_tool
from .improvement import native_tool
from .web.registration import definitions as web_definitions


def definitions():
    native = (
_definition(
            "read-tool",
            layer="capability",
            family="tools",
            label="Read files",
            description="Read text or image files from the selected environment.",
            install=_install_read_tool,
            implementation_path='fruitfly_agent/lab/tools/methods/read/algorithm.py',
            default_resource=('fruitfly_agent.lab.tools.methods.read', 'defaults.yaml'),
            documentation_path='fruitfly_agent/lab/tools/README.md',
            default=True,
            order=20,
            requires_capabilities=frozenset({"execution-env"}),
            effects=MechanismEffects(tools=("read",)), provides=frozenset({"resource-reader"}),
        feature_path=(TOOLS, FILES),
),
_definition(
            "bash-tool",
            layer="capability",
            family="tools",
            label="Run shell commands",
            description="Execute shell commands in the selected environment.",
            install=_install_bash_tool,
            parameters=(ParameterDescriptor('default_timeout_seconds', 'number', 'Command timeout', 'Default seconds per shell command.', parameter_default('fruitfly_agent.lab.tools.methods.bash', 'defaults.yaml', 'settings.default_timeout_seconds'), minimum=1, maximum=28800),
                ParameterDescriptor('max_active_commands', 'integer', 'Active commands', 'Runtime-owned managed shell jobs.', parameter_default('fruitfly_agent.lab.tools.methods.bash', 'defaults.yaml', 'settings.max_active_commands'), minimum=1, maximum=16),
                ParameterDescriptor('retained_commands', 'integer', 'Command handles', 'Maximum retained command handles.', parameter_default('fruitfly_agent.lab.tools.methods.bash', 'defaults.yaml', 'settings.retained_commands'), minimum=16, maximum=256),
                ParameterDescriptor('output_characters', 'integer', 'Poll output', 'Maximum characters per managed poll.', parameter_default('fruitfly_agent.lab.tools.methods.bash', 'defaults.yaml', 'settings.output_characters'), minimum=100, maximum=24000)),
            implementation_path='fruitfly_agent/lab/tools/methods/bash/algorithm.py',
            documentation_path='fruitfly_agent/lab/tools/README.md',
            default=True,
            order=21,
            requires_capabilities=frozenset({"execution-env"}),
            effects=MechanismEffects(tools=("bash",)),
            default_resource=('fruitfly_agent.lab.tools.methods.bash', 'defaults.yaml'),
        feature_path=(TOOLS, FILES),
),
_definition(
            "edit-tool",
            layer="capability",
            family="tools",
            label="Edit files",
            description="Apply precise replacements to existing text files.",
            install=_install_edit_tool,
            implementation_path='fruitfly_agent/lab/tools/methods/edit/algorithm.py',
            default_resource=('fruitfly_agent.lab.tools.methods.edit', 'defaults.yaml'),
            documentation_path='fruitfly_agent/lab/tools/README.md',
            default=True,
            order=22,
            requires_capabilities=frozenset({"execution-env"}),
            effects=MechanismEffects(tools=("edit",)),
        feature_path=(TOOLS, FILES),
),
_definition(
            "write-tool",
            layer="capability",
            family="tools",
            label="Write files",
            description="Create or replace files in the selected environment.",
            install=_install_write_tool,
            implementation_path='fruitfly_agent/lab/tools/methods/write/algorithm.py',
            default_resource=('fruitfly_agent.lab.tools.methods.write', 'defaults.yaml'),
            documentation_path='fruitfly_agent/lab/tools/README.md',
            default=True,
            order=23,
            requires_capabilities=frozenset({"execution-env"}),
            effects=MechanismEffects(tools=("write",)),
        feature_path=(TOOLS, FILES),
),
_definition(
            "ipython-tool",
            layer="capability",
            family="tools",
            label="Persistent IPython",
            description="Run Python in a persistent Session workspace with artifacts and bounded model queries.",
            install=install_ipython_tool,
            implementation_path='fruitfly_agent/lab/tools/methods/ipython/runtime.py',
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
            default_resource=('fruitfly_agent.lab.tools.methods.ipython', 'defaults.yaml'),
        feature_path=(TOOLS, IPYTHON),
),)
    fields = {'bash-tool': {'default_timeout_seconds'},
        'ipython-tool': {'max_query_inline_result_chars', 'max_query_concurrent', 'max_artifact_bytes',
            'max_query_input_chars', 'max_cell_output_chars', 'cell_timeout_seconds', 'query_timeout_seconds',
            'max_query_output_tokens', 'usage_instructions', 'query_instructions'}}
    return (*tuple(native_tool(d, fields.get(d.descriptor.mechanism_id, ())) for d in native), *web_definitions())


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

def _install_read_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    return _append_tool(state, create_read_tool(context.media_writer, resources=context.resources))

def _install_bash_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    from fruitfly_agent.lab.tools.commands import CommandManager
    manager = context.own(CommandManager(max_active=parameters['max_active_commands'],
        retained_commands=parameters['retained_commands'], output_characters=parameters['output_characters']))
    return _append_tool(state, create_bash_tool(default_timeout_seconds=parameters['default_timeout_seconds'], manager=manager)).with_component(
        'managed-operations', manager.operations)

def _install_edit_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    return _append_tool(state, create_edit_tool())

def _install_write_tool(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    return _append_tool(state, create_write_tool(context.media_reader))

def _append_tool(state: AssemblyState, tool) -> AssemblyState:
    return replace(state, config=replace(state.config, tools=(*state.config.tools, tool)))

