"""Strict policy values; integrity and retry ceilings are not optimization fields."""
from dataclasses import dataclass, field
import math
from .prompts import SUMMARY, READBACK


@dataclass(frozen=True)
class LayeredCompactionConfig:
    mode: str = field(default='deterministic', metadata={'description': 'Deterministic archiving, or hybrid with an explicitly bound summary model.', 'choices': ('deterministic', 'hybrid'), 'advanced': False})
    summary_model_profile: str = field(default='', metadata={'description': 'Protected summary model alias, bound through models.roles.context_summary.', 'advanced': False})
    trigger_ratio: float = field(default=.75, metadata={'description': 'Fraction of available input capacity that triggers history compaction.', 'minimum': .1, 'maximum': .95})
    target_ratio: float = field(default=.5, metadata={'description': 'Target input-capacity fraction after compaction; lower than trigger_ratio.', 'minimum': .05, 'maximum': .9})
    tool_result_min_chars: int = field(default=4000, metadata={'description': 'Minimum old tool-result text length eligible for preview and reference replacement.', 'minimum': 256, 'maximum': 64000})
    preview_chars: int = field(default=1024, metadata={'description': 'Total head and tail characters retained in an abbreviated tool result.', 'minimum': 128, 'maximum': 8192})
    keep_recent_groups: int = field(default=3, metadata={'description': 'Minimum recent complete message groups retained; tool calls and results stay together.', 'minimum': 1, 'maximum': 32})
    tail_tokens: int = field(default=8192, metadata={'description': 'Soft token target for recent complete groups, subject to input capacity.', 'minimum': 256, 'maximum': 65536})
    summary_target_tokens: int = field(default=1024, metadata={'description': 'Desired summary text size, enforced after generation.', 'minimum': 128, 'maximum': 8192})
    summary_max_output_tokens: int = field(default=4096, metadata={'description': 'Maximum auxiliary output allowance, including any protocol-specific reasoning allocation.', 'minimum': 256, 'maximum': 16384})
    summary_input_max_tokens: int = field(default=16384, metadata={'description': 'Maximum measured summary input; oversized entries become explicit source references.', 'minimum': 2048, 'maximum': 131072})
    summary_timeout_seconds: float = field(default=20., metadata={'description': 'Total seconds for summary measurement, request, stream and ordinary cleanup; cannot extend an outer task deadline.', 'minimum': 1., 'maximum': 60.})
    summary_instructions: str = field(default=SUMMARY, metadata={'description': 'Guide preservation of goals, corrections, evidence, uncertainty and remaining work in a summary.'})
    readback_instructions: str = field(default=READBACK, metadata={'description': 'Guide when to read archived original evidence rather than infer or repeat operations.'})

    def __post_init__(self):
        if self.mode not in ('deterministic', 'hybrid'):
            raise ValueError('mode must be deterministic or hybrid')
        if not isinstance(self.summary_model_profile, str) or len(self.summary_model_profile) > 200 or self.summary_model_profile.strip() != self.summary_model_profile:
            raise ValueError('summary model must be a catalog alias')
        for name in ('summary_instructions', 'readback_instructions'):
            value = getattr(self, name)
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 12000:
                raise ValueError(name + ' must contain 1 to 12000 characters')
        for name, lower, upper in (
                ('tool_result_min_chars', 256, 64000), ('preview_chars', 128, 8192),
                ('keep_recent_groups', 1, 32), ('tail_tokens', 256, 65536),
                ('summary_target_tokens', 128, 8192), ('summary_max_output_tokens', 256, 16384),
                ('summary_input_max_tokens', 2048, 131072)):
            value = getattr(self, name)
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError('invalid layered-compaction ' + name)
        for name, minimum, maximum in (('trigger_ratio', .1, .95), ('target_ratio', .05, .9),
                                   ('summary_timeout_seconds', 1., 60.)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
                raise ValueError('invalid layered-compaction ' + name)
        if self.target_ratio >= self.trigger_ratio:
            raise ValueError('target_ratio must be lower than trigger_ratio')
        if self.summary_target_tokens > self.summary_max_output_tokens:
            raise ValueError('summary target cannot exceed its output allowance')
