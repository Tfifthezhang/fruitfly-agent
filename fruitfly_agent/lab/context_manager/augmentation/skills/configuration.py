"""Skill catalog parameters: usage and projection size share one owner."""
from fruitfly_agent.runtime_spec.documents import parameter_default
from fruitfly_agent.core.mechanisms import ParameterDescriptor




def parameters():
    return (ParameterDescriptor('root', 'string', 'Skill root', 'Fixed workspace source for discovered Skill files.', parameter_default(__package__, 'skill-catalog.yaml', 'settings.root')),
            ParameterDescriptor('usage', 'string', 'Usage instructions', 'How to select and use discovered Skills; metadata remains source-owned.', parameter_default(__package__, 'skill-catalog.yaml', 'instructions.usage')),
            ParameterDescriptor('max_chars', 'integer', 'Maximum catalog characters',
                'Maximum complete projected guidance and catalog; oversized content is omitted.', parameter_default(__package__, 'skill-catalog.yaml', 'settings.max_chars'), minimum=128, maximum=1000000))
