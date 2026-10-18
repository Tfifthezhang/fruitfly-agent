"""Frozen environment knowledge learned through explicit verified practice."""
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, ParameterDescriptor
from fruitfly_agent.lab.algorithms.retained import install_retained

LEARNED_MEMORY = 'learned-memory'


def definition():
    from fruitfly_agent.lab.catalog.models import MechanismDefinition
    return MechanismDefinition(MechanismDescriptor(LEARNED_MEMORY, 'Learned environment memory',
        'Reuse verified procedures, constraints and failure lessons from explicit exploration.',
        contributions=(MechanismContribution('online', 'context', 'augmentation'),),
        parameters=(ParameterDescriptor('initial_text', 'string', 'Initial memory text',
            'Starting persistent knowledge. Adopted artifacts take precedence; file memory is unchanged.',
            '# Environment memory\nNo verified environment knowledge recorded yet.'),
            ParameterDescriptor('max_chars', 'integer', 'Memory characters',
                'Maximum complete memory document projected into context.', 16000, minimum=128, maximum=30000)),
        install_order=33), _install, implementation_id='retained-memory-v1',
        artifact_slots=frozenset({LEARNED_MEMORY}),
        implementation_path='fruitfly_agent/lab/context_manager/augmentation/information/file_memory/learned.py',
        documentation_path='fruitfly_agent/lab/context_manager/augmentation/information/file_memory/README.md',
        input_parameters=('initial_text',))


def _install(state, context, parameters):
    return install_retained(state, context, key=LEARNED_MEMORY, label='Environment memory',
        schema='environment-memory-v1', initial=parameters['initial_text'], max_chars=parameters['max_chars'])
