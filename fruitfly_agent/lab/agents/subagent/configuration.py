"""Typed protocol and result controls derived from the owning default resource."""
from dataclasses import dataclass, field, asdict
import math
from fruitfly_agent.runtime_spec.documents import parameter_default

RESOURCE = ('fruitfly_agent.lab.agents.subagent.methods.managed', 'defaults.yaml')


def default(path):
    return parameter_default(*RESOURCE, path)


@dataclass(frozen=True)
class ProtocolSettings:
    max_task_characters: int = field(default_factory=lambda: default('settings.protocol.max_task_characters'))
    max_context_characters: int = field(default_factory=lambda: default('settings.protocol.max_context_characters'))
    max_message_characters: int = field(default_factory=lambda: default('settings.protocol.max_message_characters'))
    default_wait_seconds: float = field(default_factory=lambda: default('settings.protocol.default_wait_seconds'))
    max_wait_seconds: float = field(default_factory=lambda: default('settings.protocol.max_wait_seconds'))

    def __post_init__(self):
        for name in ('max_task_characters', 'max_context_characters', 'max_message_characters'):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 16000:
                raise ValueError('subagent text limits must be integers in 1..16000')
        for value in (self.default_wait_seconds, self.max_wait_seconds):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 60:
                raise ValueError('subagent wait limits must be finite seconds in 0..60')
        if self.max_wait_seconds < .01:
            raise ValueError('maximum subagent wait must be at least .01 seconds')
        if self.default_wait_seconds > self.max_wait_seconds:
            raise ValueError('default subagent wait exceeds its maximum')

    @classmethod
    def from_parameters(cls, values):
        return cls(**{name: values[name] for name in cls.__dataclass_fields__ if name in values})


@dataclass(frozen=True)
class ResultSettings:
    output_page_characters: int = field(default_factory=lambda: default('settings.results.output_page_characters'))
    summary_characters: int = field(default_factory=lambda: default('settings.results.summary_characters'))
    task_preview_characters: int = field(default_factory=lambda: default('settings.results.task_preview_characters'))
    summary_preview_characters: int = field(default_factory=lambda: default('settings.results.summary_preview_characters'))
    max_preview_characters: int = field(default_factory=lambda: default('settings.results.max_preview_characters'))
    default_list_entries: int = field(default_factory=lambda: default('settings.results.default_list_entries'))
    max_list_entries: int = field(default_factory=lambda: default('settings.results.max_list_entries'))

    def __post_init__(self):
        for name, value in asdict(self).items():
            maximum = 50 if name.endswith('entries') else 24000
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError('subagent result controls exceed supported positive integer bounds')
        if self.default_list_entries > self.max_list_entries:
            raise ValueError('default subagent list size exceeds its maximum')
        if self.summary_preview_characters > self.summary_characters:
            raise ValueError('subagent summary preview exceeds retained summary size')

    @classmethod
    def from_parameters(cls, values):
        return cls(**{name: values[name] for name in cls.__dataclass_fields__ if name in values})


@dataclass(frozen=True)
class InheritanceSettings:
    mode: str = field(default_factory=lambda: default('settings.inheritance.mode'))
    components: tuple[str, ...] = field(default_factory=lambda: tuple(default('settings.inheritance.components')))

    def __post_init__(self):
        if self.mode not in {'parent', 'explicit'}:
            raise ValueError('subagent inheritance mode must be parent or explicit')
        if (not isinstance(self.components, (list, tuple))
                or any(not isinstance(v, str) or not v.strip() for v in self.components)
                or len(set(self.components)) != len(self.components)
                or 'subagent' in self.components):
            raise ValueError('subagent components must be distinct and cannot include delegation')
        if self.mode == 'parent' and self.components:
            raise ValueError('explicit component selection requires explicit inheritance mode')
        object.__setattr__(self, 'components', tuple(self.components))

    @classmethod
    def from_parameters(cls, values):
        return cls(mode=values.get('inheritance_mode', default('settings.inheritance.mode')),
            components=values.get('inherited_components', default('settings.inheritance.components')))
