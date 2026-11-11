"""Owner-validated presentation controls; evidence authority remains separate."""
from dataclasses import dataclass, field, asdict
from fruitfly_agent.runtime_spec.documents import mapping, parameter_default


@dataclass(frozen=True)
class EvaluatorSettings:
    output_preview_characters: int = field(default_factory=lambda: parameter_default(__package__ + '.methods.model', 'defaults.yaml', 'settings.output_preview_characters'))
    task_preview_characters: int = field(default_factory=lambda: parameter_default(__package__ + '.methods.model', 'defaults.yaml', 'settings.task_preview_characters'))
    minimum_input_characters: int = field(default_factory=lambda: parameter_default(__package__ + '.methods.model', 'defaults.yaml', 'settings.minimum_input_characters'))
    input_characters_per_token: int = field(default_factory=lambda: parameter_default(__package__ + '.methods.model', 'defaults.yaml', 'settings.input_characters_per_token'))
    task_input_divisor: int = field(default_factory=lambda: parameter_default(__package__ + '.methods.model', 'defaults.yaml', 'settings.task_input_divisor'))

    def __post_init__(self):
        if any(type(v) is not int or not 1 <= v <= 24000 for v in asdict(self).values()):
            raise ValueError('role presentation settings require bounded positive integers')
        if self.input_characters_per_token > 4 or self.task_input_divisor < 2:
            raise ValueError('invalid initial evidence allocation')

    @classmethod
    def from_dict(cls, value=None):
        if isinstance(value, cls):
            return value
        return cls(**mapping({} if value is None else value, cls.__dataclass_fields__, 'role settings'))
