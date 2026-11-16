"""Owner admission for work-product guidance; storage and grants stay protected."""
from fruitfly_agent.lab.catalog.adapters.parameters import editable_parameters


def register(definition):
    return editable_parameters(definition, frozenset({'checkpoint', 'catalog', 'read', 'patch'}))
