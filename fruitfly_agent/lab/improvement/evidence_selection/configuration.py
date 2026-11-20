"""Strict settings; installed defaults have one owner."""
from dataclasses import dataclass, field, asdict
from fruitfly_agent.runtime_spec.documents import parameter_default, mapping

PACKAGE = __package__ + '.methods.representative'
OPTIONAL_CATEGORIES = ('outputs', 'termination', 'usage', 'capture')
MATERIAL_POLICIES = ('trajectory-only', 'focused', 'all-granted')
LIMITS = {'max_cases': (1, 4096), 'controls': (0, 4096), 'max_per_task': (1, 16),
          'slow_seconds': (1, 86400), 'many_calls': (1, 10000), 'many_tools': (1, 100000), 'high_tokens': (1, 100000000)}


def default(name):
    return field(default_factory=lambda: parameter_default(PACKAGE, 'defaults.yaml', 'settings.' + name))


@dataclass(frozen=True)
class SelectionSettings:
    max_cases: int = default('max_cases')
    controls: int = default('controls')
    max_per_task: int = default('max_per_task')
    slow_seconds: int = default('slow_seconds')
    many_calls: int = default('many_calls')
    many_tools: int = default('many_tools')
    high_tokens: int = default('high_tokens')
    material_policy: str = default('material_policy')
    sampling_policy: str = default('sampling_policy')

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key == 'sampling_policy':
                if value not in ('balanced', 'rare-first', 'all'):
                    raise ValueError('invalid evidence sampling policy')
                continue
            if key == 'material_policy':
                if value not in MATERIAL_POLICIES:
                    raise ValueError('invalid evidence material policy')
                continue
            low, high = LIMITS[key]
            if type(value) is not int or not low <= value <= high:
                raise ValueError('invalid evidence selection setting: ' + key)
        if self.controls > self.max_cases:
            raise ValueError('control reservation exceeds case limit')

    @classmethod
    def from_parameters(cls, parameters):
        mapping(parameters, {'settings'}, 'evidence selection parameters')
        values = mapping(parameters.get('settings', {}), cls.__dataclass_fields__, 'evidence selection settings')
        return cls(**values)


MATERIAL_PACKAGE = __package__ + '.methods.focused'


@dataclass(frozen=True)
class MaterialSettings:
    material_policy: str = field(default_factory=lambda: parameter_default(
        MATERIAL_PACKAGE, 'defaults.yaml', 'settings.material_policy'))
    optional_categories: tuple[str, ...] = field(default_factory=lambda: parameter_default(
        MATERIAL_PACKAGE, 'defaults.yaml', 'settings.optional_categories'))

    def __post_init__(self):
        if self.material_policy not in MATERIAL_POLICIES:
            raise ValueError('invalid evidence material policy')
        categories = self.optional_categories
        if (not isinstance(categories, (list, tuple))
                or any(category not in OPTIONAL_CATEGORIES for category in categories)
                or len(categories) != len(set(categories))):
            raise ValueError('invalid optional evidence categories')
        object.__setattr__(self, 'optional_categories', tuple(sorted(categories)))

    @classmethod
    def from_parameters(cls, parameters):
        mapping(parameters, {'settings'}, 'evidence selection parameters')
        settings = parameters.get('settings', {})
        if isinstance(settings, dict):
            obsolete = set(settings) & (set(LIMITS) | {'sampling_policy'})
            if obsolete:
                raise ValueError('execution selection belongs to grouping; remove evidence settings: '
                                 + ', '.join(sorted(obsolete)))
        return cls(**mapping(settings, cls.__dataclass_fields__, 'evidence material settings'))
