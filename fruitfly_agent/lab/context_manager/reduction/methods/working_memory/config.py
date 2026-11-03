"""Strict working-memory policy; checkpoint integrity is not editable."""
from fruitfly_agent.runtime_spec.documents import parameter_default
from dataclasses import dataclass, field
import math


@dataclass(frozen=True)
class WorkingMemoryConfig:
    update_instructions: str = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'instructions.update'), metadata={'description': 'Merge new evidence into task memory: preserve requirements, corrections, decisions, failures, and unresolved work.', 'advanced': False})
    shrink_instructions: str = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'instructions.shrink'), metadata={'description': 'Shorten oversized task memory while preserving necessary facts and explicit uncertainty.', 'advanced': False})
    readback_instructions: str = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'instructions.readback'), metadata={'description': 'Guide when to read original evidence after context reduction.', 'advanced': False})
    memory_model_profile: str = field(default='', metadata={'description': 'Model role alias; default inherits executor.', 'advanced': False})
    maintenance_ratio: float = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'settings.maintenance_ratio'), metadata={'description': 'Minimum available-input fraction for periodic maintenance.', 'minimum': 0., 'maximum': 1.})
    update_timeout_seconds: float = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'settings.update_timeout_seconds'), metadata={'description': 'Total update budget across pages, measurement, retries and shortening.', 'minimum': .01, 'maximum': 600.})
    memory_tokens: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'settings.memory_tokens'), metadata={'description': 'Target task-memory token capacity; larger memory retains more content but consumes request context.', 'advanced': False, 'minimum': 1, 'maximum': 32000})
    update_every_messages: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'settings.update_every_messages'), metadata={'description': 'New canonical messages between memory updates; frequent updates can increase auxiliary model work.', 'advanced': False, 'minimum': 1, 'maximum': 1024})
    switch_ratio: float = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'settings.switch_ratio'), metadata={'description': 'Input-capacity ratio that triggers an update or projection switch; integrity and coverage checks still apply.', 'advanced': False, 'minimum': 0.1, 'maximum': 1})
    page_char_limit: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'settings.page_char_limit'), metadata={'description': 'Maximum source characters per evidence page sent to a memory update.', 'advanced': True, 'minimum': 1, 'maximum': 120000})
    max_pages: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'settings.max_pages'), metadata={'description': 'Maximum evidence pages per update; unprocessed pages never count as covered.', 'advanced': True, 'minimum': 1, 'maximum': 128})
    auxiliary_max_tokens: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'settings.auxiliary_max_tokens'), metadata={'description': 'Maximum output tokens per auxiliary memory response; does not raise the main task allowance.', 'advanced': True, 'minimum': 1, 'maximum': 64000})
    auxiliary_attempts: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'settings.auxiliary_attempts'), metadata={'description': 'Maximum attempts for an auxiliary memory update, within the outer hard allowance.', 'advanced': True, 'minimum': 1, 'maximum': 8})
    auxiliary_timeout_seconds: float = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'settings.auxiliary_timeout_seconds'), metadata={'description': 'Seconds allowed for one auxiliary update; cannot extend the task deadline.', 'advanced': True, 'minimum': 0.01, 'maximum': 600})

    def __post_init__(self):
        if not isinstance(self.memory_model_profile, str):
            raise ValueError('memory model alias must be a string')
        for name in ('update_instructions', 'shrink_instructions', 'readback_instructions'):
            value = getattr(self, name)
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 12000:
                raise ValueError(name + ' must contain 1 to 12000 characters')
        for name, maximum in (('memory_tokens', 32000), ('update_every_messages', 1024),
                ('page_char_limit', 120000), ('max_pages', 128), ('auxiliary_max_tokens', 64000), ('auxiliary_attempts', 8)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError('invalid working-memory ' + name)
        for name, minimum, maximum in (('maintenance_ratio', 0, 1), ('update_timeout_seconds', .01, 600), ('switch_ratio', .1, 1), ('auxiliary_timeout_seconds', .01, 600)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not minimum <= value <= maximum:
                raise ValueError('invalid working-memory ' + name)
        if self.maintenance_ratio > self.switch_ratio:
            raise ValueError('maintenance_ratio must not exceed switch_ratio')
