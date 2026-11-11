"""Owner-validated presentation controls; evidence authority remains separate."""
from dataclasses import dataclass, field, asdict
from fruitfly_agent.runtime_spec.documents import mapping, parameter_default


@dataclass(frozen=True)
class EditorSettings:
    target_page_entries: int = field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'settings.target_page_entries'))
    max_target_entries: int = field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'settings.max_target_entries'))

    def __post_init__(self):
        if any(type(v) is not int or not 1 <= v <= 24000 for v in asdict(self).values()):
            raise ValueError('role presentation settings require bounded positive integers')
        if not self.target_page_entries <= self.max_target_entries <= 100:
            raise ValueError('target pages require default <= maximum <= 100')

    @classmethod
    def from_dict(cls, value=None):
        if isinstance(value, cls):
            return value
        return cls(**mapping({} if value is None else value, cls.__dataclass_fields__, 'role settings'))
