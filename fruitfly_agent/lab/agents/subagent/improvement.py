"""Owner-controlled instruction candidates use ordinary configuration assembly."""
from fruitfly_agent.lab.catalog.adapters.parameters import editable_parameters

FIELDS = frozenset({'child_instructions', *(name + '_instructions' for name in ('spawn', 'send', 'wait', 'status', 'cancel'))})

def register(definition):
    return editable_parameters(definition, FIELDS)
