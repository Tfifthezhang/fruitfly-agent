"""One H target for usage instructions and catalog projection size."""
from fruitfly_agent.lab.improvement.components.parameters import editable_parameters


def register(definition):
    return editable_parameters(definition, {'usage', 'max_chars'})
