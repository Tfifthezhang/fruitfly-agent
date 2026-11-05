"""Public owner registration entry for memory H/S and maintenance I surfaces."""
from .registration import definitions as memory_definitions
from .methods.threshold_maintenance.registration import definitions as maintenance_definitions


def definitions():
    return (*memory_definitions(), *maintenance_definitions())


def comparison_definition():
    from .methods.threshold_maintenance.comparison import definition
    return definition()


__all__ = ['definitions', 'comparison_definition']
