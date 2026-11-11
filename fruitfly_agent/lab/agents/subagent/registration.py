"""One H component owns delegation controls and the subagent model role."""
from typing import cast
from fruitfly_agent.core.mechanisms import ParameterKind
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects, ParameterDescriptor
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from fruitfly_agent.lab.catalog.model_roles import ModelRoleRequirement
from fruitfly_agent.lab.catalog.classification import AGENTS
from fruitfly_agent.runtime_spec.documents import parameter_default
from fruitfly_agent.improvement.contracts.text import validate_text
from .improvement import register, FIELDS
from .workers import worker_definitions
from .configuration import ProtocolSettings, ResultSettings, InheritanceSettings
from .methods.managed.algorithm import install

RESOURCE = ('fruitfly_agent.lab.agents.subagent.methods.managed', 'defaults.yaml')
RESEARCH_INSTRUCTIONS = frozenset({'evidence_child_instructions', 'evidence_parent_instructions'})
INSTRUCTIONS = FIELDS | RESEARCH_INSTRUCTIONS

def definition():
    parameters = tuple(ParameterDescriptor(name, cast(ParameterKind, kind), label, description,
        parameter_default(*RESOURCE, 'settings.' + name), minimum=minimum, maximum=maximum)
        for name, kind, label, description, minimum, maximum in (
            ('max_concurrent', 'integer', 'Concurrent subagents', 'Active child executions per parent task.', 1, 8),
            ('max_agents', 'integer', 'Subagent sessions', 'Maximum child sessions created per parent task.', 1, 32),
            ('run_timeout_seconds', 'number', 'Execution deadline', 'Seconds including queue, construction and model work.', .01, 3600),
            ('max_model_requests', 'integer', 'Model requests', 'Maximum requests in each child execution.', 1, 512),
            ('retirement_timeout', 'number', 'Retirement deadline', 'Seconds to confirm owned resource cleanup.', .01, 60)))
    for group, kind in (('protocol', ProtocolSettings), ('results', ResultSettings)):
        for name in kind.__dataclass_fields__:
            number = name.endswith('seconds')
            maximum = 60 if number else 50 if name.endswith('entries') else 16000 if name.startswith('max_') and name.endswith('characters') and group == 'protocol' else 24000
            parameters += (ParameterDescriptor(name, 'number' if number else 'integer', name.replace('_', ' ').capitalize(),
                'Delegation ' + group + ' control applied to schemas and execution.',
                parameter_default(*RESOURCE, 'settings.' + group + '.' + name), minimum=.01 if name == 'max_wait_seconds' else 0 if number else 1, maximum=maximum),)
    parameters += (ParameterDescriptor('workers', 'object', 'Named research workers',
        'Complete named worker definitions with role, instructions, capabilities, inheritance, limits and result contract.',
        parameter_default(*RESOURCE, 'settings.workers')), )
    parameters += (
        ParameterDescriptor('evidence_tools', 'string_list', 'Research evidence tools',
            'Read-only tools exposed to assigned-evidence children.',
            parameter_default(*RESOURCE, 'settings.research.tools')),
        *(ParameterDescriptor(name, 'choice', label, description,
            parameter_default(*RESOURCE, 'settings.research.' + key), choices=(value,))
            for name, key, value, label, description in (
                ('evidence_resources', 'resources', 'assigned', 'Research resources', 'Children read only explicitly assigned immutable materials.'),
                ('evidence_writes', 'writes', 'deny', 'Research writes', 'Read-only investigation cannot write candidate or workspace files.'),
                ('evidence_conversation', 'conversation', 'explicit_materials', 'Research conversation', 'Pass explicit task/context; do not inherit the parent conversation.'))))
    parameters += (
        ParameterDescriptor('inheritance_mode', 'choice', 'Child component inheritance',
            'Use parent components or an explicit subset; host authorization is retained.',
            parameter_default(*RESOURCE, 'settings.inheritance.mode'), choices=('parent', 'explicit')),
        ParameterDescriptor('inherited_components', 'string_list', 'Explicit child components',
            'Enabled parent component IDs to retain in explicit mode; never adds authority.',
            parameter_default(*RESOURCE, 'settings.inheritance.components')))
    parameters += (ParameterDescriptor('model_profile', 'string', 'Subagent model', 'Model role alias; default inherits executor.', ''),)
    parameters += tuple(ParameterDescriptor(name, 'string', name.replace('_', ' ').capitalize(),
        'Model-facing subagent instructions; identity, schemas and permissions remain protected.',
        parameter_default(*RESOURCE, 'instructions.' + name.removesuffix('_instructions'))) for name in sorted(INSTRUCTIONS))
    return register(MechanismDefinition(MechanismDescriptor('subagent', 'Subagent',
        'Delegate independent tasks to bounded child Agents with private conversations and observable results.',
        contributions=(MechanismContribution('capability', 'tools'),), parameters=parameters, install_order=200,
        effects=MechanismEffects(uses_provider=True, uses_network=True, writes_files=True,
            tools=tuple('subagent_' + name for name in ('spawn', 'send', 'wait', 'status', 'cancel')),
            cost_notice='Subagents make independent model requests and may execute tools in the shared workspace.')),
        install, default_resource=RESOURCE, feature_path=(AGENTS,), implementation_id='subagent-managed-v1',
        implementation_path='fruitfly_agent/lab/agents/subagent/methods/managed/algorithm.py',
        documentation_path='fruitfly_agent/lab/agents/subagent/README.md',
        model_role_parameters={'subagent': ModelRoleRequirement('model_profile', 'Execute delegated tasks.')},
        parameter_paths={p.name: 'instructions.' + p.name.removesuffix('_instructions') if p.name in INSTRUCTIONS else 'settings.protocol.' + p.name if p.name in ProtocolSettings.__dataclass_fields__
            else 'settings.results.' + p.name if p.name in ResultSettings.__dataclass_fields__
            else 'settings.inheritance.mode' if p.name == 'inheritance_mode'
            else 'settings.inheritance.components' if p.name == 'inherited_components'
            else 'settings.research.' + {'evidence_tools': 'tools', 'evidence_resources': 'resources',
                'evidence_writes': 'writes', 'evidence_conversation': 'conversation'}[p.name] if p.name.startswith('evidence_')
            else 'settings.' + p.name for p in parameters},
        validate_parameters=validate))

def validate(parameters):
    worker_definitions(parameters)
    tools = parameters.get('evidence_tools', parameter_default(*RESOURCE, 'settings.research.tools'))
    if (not isinstance(tools, (list, tuple)) or any(not isinstance(v, str) or v not in {'catalog', 'search', 'read'} for v in tools)
            or len(set(tools)) != len(tools)):
        raise ValueError('research tools must be a distinct subset of catalog/search/read')
    InheritanceSettings.from_parameters(parameters)
    ProtocolSettings.from_parameters(parameters)
    ResultSettings.from_parameters(parameters)
    for name in INSTRUCTIONS:
        if name in parameters:
            validate_text(parameters[name])
