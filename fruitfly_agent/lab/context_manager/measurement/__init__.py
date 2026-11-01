"""Shared request measurement infrastructure, independent of selectable mechanisms."""
from copy import deepcopy


def new_measurement_scope(meter):
    """Reset owner-declared runtime state, or isolate a custom meter's initial state."""
    if meter is None:
        return None
    create = getattr(meter, 'new_scope', None)
    return create() if callable(create) else deepcopy(meter)
