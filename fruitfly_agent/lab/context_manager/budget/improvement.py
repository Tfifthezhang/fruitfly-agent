"""Only reduction thresholds are candidate editable; the host ceiling is protected."""
from fruitfly_agent.lab.catalog.adapters.parameters import editable_parameters


def register(definition):
    return editable_parameters(definition, {'trigger_ratio', 'target_ratio'}, default_selected=False)
