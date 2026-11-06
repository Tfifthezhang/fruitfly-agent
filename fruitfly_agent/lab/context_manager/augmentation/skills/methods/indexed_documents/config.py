"""Skill catalog parameters: usage and projection size share one owner."""
from fruitfly_agent.runtime_spec.documents import parameter_default
from fruitfly_agent.core.mechanisms import ParameterDescriptor




def parameters():
    return (ParameterDescriptor('root', 'string', 'Skill root', 'Fixed workspace source for discovered Skill files.', parameter_default(__package__, 'defaults.yaml', 'settings.root')),
            ParameterDescriptor('usage', 'string', 'Usage instructions', 'How to select and use discovered Skills; metadata remains source-owned.', parameter_default(__package__, 'defaults.yaml', 'instructions.usage')),
            ParameterDescriptor('max_chars', 'integer', 'Maximum catalog characters',
                'Bound projected metadata; oversized directories stay readable through a complete resource reference.', parameter_default(__package__, 'defaults.yaml', 'settings.max_chars'), minimum=256, maximum=1000000))
