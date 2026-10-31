"""Working-memory method's configuration and Improvement admission."""
from dataclasses import replace
from functools import partial
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from ....registration import parameters, validate
from ...improvement import expose
from .algorithm import WorkingMemoryReducer
from .config import WorkingMemoryConfig


def definition():
    root = 'fruitfly_agent/lab/context_manager/reduction/methods/working_memory/'
    value = MechanismDefinition(MechanismDescriptor('working-memory-reduction', 'Working memory',
        'Incrementally maintain bounded task memory and reset only after complete evidence coverage.',
        contributions=(MechanismContribution('online', 'context', 'reduction'),), default_enabled=True, install_order=60,
        parameters=parameters(WorkingMemoryConfig), exclusive_group='compaction', requires=frozenset({'context-history'}),
        effects=MechanismEffects(uses_provider=True, uses_network=True, writes_files=True,
            lifecycle_hooks=('before_compaction',),
            cost_notice='Memory updates and shortening requests may incur Provider charges.')),
        install, implementation_id='working-memory-v1', implementation_path=root + 'algorithm.py',
        documentation_path=root + 'README.md', selection_group='reduction', selection_group_label='Reduction',
        validate_parameters=partial(validate, WorkingMemoryConfig))
    value=replace(value,parameter_paths={name: ('instructions.update' if name=='update_instructions' else 'instructions.shrink' if name=='shrink_instructions' else 'settings.'+name) for name in WorkingMemoryConfig.__dataclass_fields__})
    return expose(value, WorkingMemoryConfig)


def install(state, context, values):
    config = WorkingMemoryConfig(**values)
    binding = context.provider_resolver(None, config.auxiliary_max_tokens)
    history = state.components['context-history']
    reducer = WorkingMemoryReducer(config, binding.provider, memory_model=binding.model,
        memory_context_window=binding.context_window, memory_output_limit=binding.max_output_tokens, history=history,
        meter=state.config.context_meter)
    return replace(state, reducer=reducer).with_component('working-memory-checkpoint', reducer)
