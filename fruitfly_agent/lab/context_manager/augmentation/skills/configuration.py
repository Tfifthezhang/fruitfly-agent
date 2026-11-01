"""Skill catalog parameters: usage and projection size share one owner."""
from fruitfly_agent.core.mechanisms import ParameterDescriptor

USAGE = ("The following skills provide specialized instructions for specific tasks. "
         "Read the full skill file when the task matches its description. "
         "Resolve relative references against the skill directory.")


def parameters():
    return (ParameterDescriptor('root', 'string', 'Skill root', 'Fixed workspace source for discovered Skill files.', '.skills'),
            ParameterDescriptor('usage', 'string', 'Usage instructions', 'How to select and use discovered Skills; metadata remains source-owned.', USAGE),
            ParameterDescriptor('max_chars', 'integer', 'Maximum catalog characters',
                'Maximum complete projected guidance and catalog; oversized content is omitted.', 16000, minimum=128, maximum=1000000))
