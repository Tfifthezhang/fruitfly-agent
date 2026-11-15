"""Declare shared context execution conditions through the ordinary Catalog."""
from dataclasses import replace
from fruitfly_agent.core.context.budget import ContextBudget
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from fruitfly_agent.lab.catalog.classification import EXECUTION
from ..registration import parameters, validate
from .improvement import register


def install(state, context, values):
    return replace(state, config=replace(state.config, context_budget=ContextBudget(**values)))


def definition():
    from functools import partial
    return register(MechanismDefinition(MechanismDescriptor('context-budget', 'Context budget',
        'Set the shared working input capacity and reduction thresholds.',
        contributions=(MechanismContribution('capability', 'context'),),
        default_enabled=True, install_order=0, parameters=parameters(ContextBudget)),
        install, implementation_id='context-budget-v1',
        execution_fields=frozenset('context_budget.' + name for name in ('max_input_tokens', 'trigger_ratio', 'target_ratio')),
        execution_projection=lambda values: {'context_budget': dict(values)},
        validate_parameters=partial(validate, ContextBudget),
        default_resource=('fruitfly_agent.core.context', 'defaults.yaml'),
        implementation_path='fruitfly_agent/lab/context_manager/budget/registration.py',
        documentation_path='fruitfly_agent/lab/context_manager/budget/README.md',
        feature_path=(EXECUTION,)))
