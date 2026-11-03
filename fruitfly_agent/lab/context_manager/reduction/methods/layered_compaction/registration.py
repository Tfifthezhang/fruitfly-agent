"""Default H reduction with optional, explicitly bound summary inference."""
from dataclasses import replace, fields
from functools import partial

from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from fruitfly_agent.lab.catalog.model_roles import ModelRoleRequirement
from ....registration import parameters, validate
from .config import LayeredCompactionConfig
from .algorithm import LayeredCompactionReducer
from .improvement import register
from .resources import install_history
from .summary import HistorySummarizer


def definition():
    root = 'fruitfly_agent/lab/context_manager/reduction/methods/layered_compaction/'
    descriptors = tuple(replace(p, kind='choice', choices=('deterministic', 'hybrid'))
                        if p.name == 'mode' else p for p in parameters(LayeredCompactionConfig))
    value = MechanismDefinition(MechanismDescriptor('layered-compaction', 'Layered compaction',
        'Shrink old results into readable references; summarize history only when explicitly configured and needed.',
        contributions=(MechanismContribution('online', 'context', 'reduction'),),
        default_enabled=True, install_order=60, parameters=descriptors,
        exclusive_group='reduction', requires=frozenset({'read-tool'}),
        effects=MechanismEffects(uses_provider=True, uses_network=True, writes_files=True,
            lifecycle_hooks=('before_compaction', 'context_activity'),
            cost_notice='Deterministic mode makes no auxiliary requests. Hybrid summaries use the selected summary model and may incur charges.')),
        install, implementation_id='layered-compaction-v1', configuration_role='H',
        implementation_path=root + 'algorithm.py', documentation_path=root + 'README.md',
        selection_group='reduction', selection_group_label='Reduction',
        input_parameters=('mode', 'summary_model_profile'), default_resource=(__package__, 'defaults.yaml'),
        validate_parameters=partial(validate, LayeredCompactionConfig),
        model_role_parameters={'context_summary': ModelRoleRequirement('summary_model_profile',
            'Summarize supplied archived evidence.', required_when=lambda values: values['mode'] == 'hybrid')})
    value = replace(value, parameter_paths={f.name: 'instructions.summary' if f.name == 'summary_instructions' else
        'instructions.readback' if f.name == 'readback_instructions' else 'settings.' + f.name
        for f in fields(LayeredCompactionConfig)})
    return register(value)


def install(state, context, values):
    config = LayeredCompactionConfig(**values)
    summarizer = None
    if config.mode == 'hybrid':
        binding = context.provider_for_role('context_summary', config.summary_max_output_tokens)
        summarizer = HistorySummarizer(binding.provider, model=binding.model,
            context_window=binding.context_window, output_limit=binding.max_output_tokens,
            meter=state.config.context_meter)
    reducer = LayeredCompactionReducer(config, history=install_history(context), summarizer=summarizer)
    return replace(state, reducer=reducer).with_component('layered-compaction-state', reducer)
