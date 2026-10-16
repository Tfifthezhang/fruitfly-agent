"""Declare material policy without running collection during assembly."""
from fruitfly_agent.core.mechanisms import MechanismContribution, MechanismDescriptor, MechanismEffects, ParameterDescriptor

LEARNING_POLICY_COMPONENT = 'learning-material-policy'
LEARNING_PROCESSOR_COMPONENT = 'learning-material-processor'


def definition():
    from fruitfly_agent.lab.catalog.models import MechanismDefinition
    return MechanismDefinition(
        MechanismDescriptor('task-material-recording', 'Record completed tasks',
            'Record bounded task observations as pending learning material; no inferred answers or scores.',
            (MechanismContribution('online', 'workflow'),),
            parameters=(
                ParameterDescriptor('trigger', 'choice', 'Collection timing', 'Process after each task, at session close, or in batches.', 'task', choices=('task', 'session', 'batch')),
                ParameterDescriptor('batch_size', 'integer', 'Batch size', 'Tasks per material batch; close also drains remaining tasks.', 4, minimum=1, maximum=100),
                ParameterDescriptor('max_records', 'integer', 'Session record limit', 'Maximum distinct observed tasks per runtime.', 100, minimum=1, maximum=1000),
                ParameterDescriptor('max_chars', 'integer', 'Material character limit', 'Skip oversized observations; reject oversized generated material.', 16000, minimum=128, maximum=100000),
            ), install_order=73,
            effects=MechanismEffects(writes_files=True,
                cost_notice='Stores task text in workspace learning records. Recording makes no model calls and starts no search.')),
        _install, implementation_id='task-material-recording-v1',
        selection_group='learning-materials', selection_group_label='Learning materials',
        configuration_category='learning')


def _install(state, context, parameters):
    return state.with_component(LEARNING_POLICY_COMPONENT, dict(parameters))
