"""Defaults for a finite evolution, without model or benchmark assembly."""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class EvolutionSettings:
    max_generations: int = 3
    continue_on_rejection: bool = False
    policy: str = 'auto'

    def __post_init__(self):
        for name in ('max_generations',):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(name + ' must be a positive integer')
        if type(self.continue_on_rejection) is not bool or not isinstance(self.policy, str) or not self.policy:
            raise ValueError('invalid evolution continuation or verification policy')
