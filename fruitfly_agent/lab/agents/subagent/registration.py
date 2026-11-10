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
from .methods.managed.algorithm import install

RESOURCE = ('fruitfly_agent.lab.agents.subagent.methods.managed', 'defaults.yaml')

def definition():
    parameters = tuple(ParameterDescriptor(name, cast(ParameterKind, kind), label, description,
        parameter_default(*RESOURCE, 'settings.' + name), minimum=minimum, maximum=maximum)
        for name, kind, label, description, minimum, maximum in (
            ('max_concurrent', 'integer', 'Concurrent subagents', 'Active child executions per parent task.', 1, 8),
            ('max_agents', 'integer', 'Subagent sessions', 'Maximum child sessions created per parent task.', 1, 32),
            ('run_timeout_seconds', 'number', 'Execution deadline', 'Seconds including queue, construction and model work.', .01, 3600),
            ('max_model_requests', 'integer', 'Model requests', 'Maximum requests in each child execution.', 1, 512)))
    parameters += (ParameterDescriptor('model_profile', 'string', 'Subagent model', 'Model role alias; default inherits executor.', ''),)
    parameters += tuple(ParameterDescriptor(name, 'string', name.replace('_', ' ').capitalize(),
        'Model-facing subagent instructions; identity, schemas and permissions remain protected.',
        parameter_default(*RESOURCE, 'instructions.' + name.removesuffix('_instructions'))) for name in sorted(FIELDS))
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
        parameter_paths={p.name: 'instructions.' + p.name.removesuffix('_instructions') if p.name in FIELDS else 'settings.' + p.name for p in parameters},
        validate_parameters=validate))

def validate(parameters):
    for name in FIELDS:
        if name in parameters:
            validate_text(parameters[name])
