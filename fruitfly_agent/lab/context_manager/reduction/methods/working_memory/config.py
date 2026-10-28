"""Strict working-memory policy; checkpoint integrity is not editable."""
from dataclasses import dataclass
import math
from .prompts import UPDATE, SHRINK


@dataclass(frozen=True)
class WorkingMemoryConfig:
    update_instructions: str = UPDATE
    shrink_instructions: str = SHRINK
    memory_tokens: int = 2048
    update_every_messages: int = 8
    switch_ratio: float = .85
    page_char_limit: int = 24000
    max_pages: int = 8
    auxiliary_max_tokens: int = 3072
    auxiliary_attempts: int = 2
    auxiliary_timeout_seconds: float = 60.0

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
