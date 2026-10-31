"""Strict working-memory policy; checkpoint integrity is not editable."""
from dataclasses import dataclass, field
import math
from .prompts import UPDATE, SHRINK


@dataclass(frozen=True)
class WorkingMemoryConfig:
    update_instructions: str = field(default=UPDATE, metadata={'description': 'Merge new evidence into task memory: preserve requirements, corrections, decisions, failures, and unresolved work.', 'advanced': False})
    shrink_instructions: str = field(default=SHRINK, metadata={'description': 'Shorten oversized task memory while preserving necessary facts and explicit uncertainty.', 'advanced': False})
    memory_tokens: int = field(default=2048, metadata={'description': 'Target task-memory token capacity; larger memory retains more content but consumes request context.', 'advanced': False, 'minimum': 1, 'maximum': 32000})
    update_every_messages: int = field(default=8, metadata={'description': 'New canonical messages between memory updates; frequent updates can increase auxiliary model work.', 'advanced': False, 'minimum': 1, 'maximum': 1024})
    switch_ratio: float = field(default=.85, metadata={'description': 'Input-capacity ratio that triggers an update or projection switch; integrity and coverage checks still apply.', 'advanced': False, 'minimum': 0.1, 'maximum': 1})
    page_char_limit: int = field(default=24000, metadata={'description': 'Maximum source characters per evidence page sent to a memory update.', 'advanced': True, 'minimum': 1, 'maximum': 120000})
    max_pages: int = field(default=8, metadata={'description': 'Maximum evidence pages per update; unprocessed pages never count as covered.', 'advanced': True, 'minimum': 1, 'maximum': 128})
    auxiliary_max_tokens: int = field(default=3072, metadata={'description': 'Maximum output tokens per auxiliary memory response; does not raise the main task allowance.', 'advanced': True, 'minimum': 1, 'maximum': 64000})
    auxiliary_attempts: int = field(default=2, metadata={'description': 'Maximum attempts for an auxiliary memory update, within the outer hard allowance.', 'advanced': True, 'minimum': 1, 'maximum': 8})
    auxiliary_timeout_seconds: float = field(default=60.0, metadata={'description': 'Seconds allowed for one auxiliary update; cannot extend the task deadline.', 'advanced': True, 'minimum': 0.01, 'maximum': 600})

    def __post_init__(self):
        for name in ('update_instructions', 'shrink_instructions'):
            value = getattr(self, name)
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 12000:
                raise ValueError(name + ' must contain 1 to 12000 characters')
        for name, maximum in (('memory_tokens', 32000), ('update_every_messages', 1024),
                ('page_char_limit', 120000), ('max_pages', 128), ('auxiliary_max_tokens', 64000), ('auxiliary_attempts', 8)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError('invalid working-memory ' + name)
        for name, minimum, maximum in (('switch_ratio', .1, 1), ('auxiliary_timeout_seconds', .01, 600)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not minimum <= value <= maximum:
                raise ValueError('invalid working-memory ' + name)
