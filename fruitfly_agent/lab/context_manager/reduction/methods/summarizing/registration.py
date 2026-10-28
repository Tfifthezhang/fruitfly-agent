"""Summarizing method's configuration, effects and Improvement admission."""
from dataclasses import replace
from functools import partial
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from ....registration import parameters, validate
from ...improvement import expose
from .algorithm import SummarizingCompactor
from .config import SummarizingCompactorConfig


def definition():
    root = 'fruitfly_agent/lab/context_manager/reduction/methods/summarizing/'
    value = MechanismDefinition(MechanismDescriptor('compaction', 'Summarizing',
        'Page complete history into a continuity summary with bounded recovery.',
        contributions=(MechanismContribution('online', 'context', 'reduction'),),
        parameters=parameters(SummarizingCompactorConfig), default_enabled=True, install_order=60, requires=frozenset({'context-history'}),
        exclusive_group='compaction', effects=MechanismEffects(uses_provider=True, uses_network=True, writes_files=True,
            lifecycle_hooks=('before_compaction',),
            cost_notice='Summary requests may incur Provider charges.')),
        install, implementation_id='summarizing-v3', implementation_path=root + 'algorithm.py',
        documentation_path=root + 'README.md', selection_group='reduction', selection_group_label='Reduction',
        validate_parameters=partial(validate, SummarizingCompactorConfig))
    return expose(value, SummarizingCompactorConfig, protected=('enabled', 'prompt_version'))


def install(state, context, values):
    config = SummarizingCompactorConfig(**values)
    binding = context.provider_resolver(None, config.summary_max_tokens)
    history = state.components['context-history']
    reducer = SummarizingCompactor(config, binding.provider, summary_model=binding.model,
        summary_context_window=binding.context_window, summary_output_limit=binding.max_output_tokens, history=history,
        meter=state.config.context_meter)
    return replace(state, reducer=reducer)
