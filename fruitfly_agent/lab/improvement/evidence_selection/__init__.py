"""Public, replaceable evidence-selection implementation and configuration."""
from .methods.representative.algorithm import RepresentativeSelector
from .configuration import SelectionSettings

__all__ = ['RepresentativeSelector', 'SelectionSettings']
