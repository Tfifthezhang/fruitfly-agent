"""Defaults for a finite evolution, without model or benchmark assembly."""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class EvolutionSettings:
    max_generations: int = 3
    phase_timeout: float = 3600
    timeout_seconds: float = 10800
    max_model_calls: int = 768
    max_executions: int = 64
    continue_on_rejection: bool = False
    policy: str = 'auto'

    def __post_init__(self):
        for name in ('max_generations', 'max_model_calls', 'max_executions'):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(name + ' must be a positive integer')
        for name in ('phase_timeout', 'timeout_seconds'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value) or value <= 0:
                raise ValueError(name + ' must be finite and positive')
        if type(self.continue_on_rejection) is not bool or not isinstance(self.policy, str) or not self.policy:
            raise ValueError('invalid evolution continuation or verification policy')
