"""Execution instructions own their configuration and optimization projection."""
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from fruitfly_agent.lab.catalog.classification import EXECUTION
from .target import configuration_surface


def definition():
    return MechanismDefinition(MechanismDescriptor('execution-instructions', 'Execution instructions',
        'Provide the base task-execution instructions through a registered text surface.',
        contributions=(MechanismContribution('capability', 'tools'),)),
        lambda state, context, parameters: state, visible=False, configurable=False,
        feature_path=(EXECUTION,), configuration_surfaces=(configuration_surface(),),
        implementation_path='fruitfly_agent/lab/base_prompt/target.py',
        documentation_path='fruitfly_agent/lab/base_prompt/README.md')
