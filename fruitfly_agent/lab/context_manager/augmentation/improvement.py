"""Owner-controlled parameter surfaces for executable candidate configuration."""
from fruitfly_agent.lab.improvement.components.parameters import editable_parameters


FIELDS = {'information-context': {'max_chars', 'top_k'}, 'skill-catalog': {'max_chars'}}


def expose(definition):
    fields = FIELDS.get(definition.descriptor.mechanism_id)
    return editable_parameters(definition, fields) if fields else definition
