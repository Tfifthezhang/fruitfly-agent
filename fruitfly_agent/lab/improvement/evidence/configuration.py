"""Strict shared evidence response limits, independent of editor/evaluator policy."""
from dataclasses import dataclass, field, asdict
import re
from fruitfly_agent.runtime_spec.documents import mapping, parameter_default


@dataclass(frozen=True)
class ReadSettings:
    default_characters: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'read.default_characters'))
    max_characters: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'read.max_characters'))


@dataclass(frozen=True)
class CatalogSettings:
    default_entries: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'catalog.default_entries'))
    max_entries: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'catalog.max_entries'))


@dataclass(frozen=True)
class SearchSettings:
    default_matches: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'search.default_matches'))
    max_matches: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'search.max_matches'))
    max_characters: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'search.max_characters'))


@dataclass(frozen=True)
class SupplySettings:
    max_characters: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'supply.max_characters'))
    max_pages: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'supply.max_pages'))
    completion_requests: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'supply.completion_requests'))


@dataclass(frozen=True)
class DelegationSettings:
    enabled: bool = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'delegation.enabled'))
    workers: tuple[str, ...] = field(default_factory=lambda: tuple(parameter_default(__package__, 'defaults.yaml', 'delegation.workers')))

    def __post_init__(self):
        if type(self.enabled) is not bool or not isinstance(self.workers, (list, tuple)):
            raise ValueError('invalid evidence delegation controls')
        if (any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', v) for v in self.workers)
                or len(set(self.workers)) != len(self.workers) or self.enabled and not self.workers):
            raise ValueError('evidence delegation requires distinct worker identifiers')
        object.__setattr__(self, 'workers', tuple(self.workers))


@dataclass(frozen=True)
class RetentionSettings:
    enabled: bool = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'retention.enabled'))
    reuse: bool = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'retention.reuse'))
    preview_characters: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'retention.preview_characters'))

    def __post_init__(self):
        if type(self.enabled) is not bool or type(self.reuse) is not bool:
            raise ValueError('retention controls must be booleans')
        if type(self.preview_characters) is not int or not 1 <= self.preview_characters <= 24000:
            raise ValueError('retention previews require a bounded positive character count')


@dataclass(frozen=True)
class SessionInstructions:
    catalog_parts: str = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'instructions.catalog_parts'))
    read_part: str = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'instructions.read_part'))
    initial: str = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'instructions.initial'))
    repair: str = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'instructions.repair'))
    catalog: str = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'instructions.catalog'))
    read: str = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'instructions.read'))
    search: str = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'instructions.search'))
    submit_findings: str = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'instructions.submit_findings'))

    def __post_init__(self):
        if any(not isinstance(v, str) or not v.strip() or len(v) > 120000 for v in asdict(self).values()):
            raise ValueError('evidence instructions require bounded nonempty text')


@dataclass(frozen=True)
class EvidenceSettings:
    read: ReadSettings = field(default_factory=ReadSettings)
    catalog: CatalogSettings = field(default_factory=CatalogSettings)
    search: SearchSettings = field(default_factory=SearchSettings)
    supply: SupplySettings = field(default_factory=SupplySettings)
    delegation: DelegationSettings = field(default_factory=DelegationSettings)
    instructions: SessionInstructions = field(default_factory=SessionInstructions)
    retention: RetentionSettings = field(default_factory=RetentionSettings)

    def __post_init__(self):
        for name, kind in (('read', ReadSettings), ('catalog', CatalogSettings), ('search', SearchSettings), ('supply', SupplySettings), ('delegation', DelegationSettings), ('instructions', SessionInstructions), ('retention', RetentionSettings)):
            value = getattr(self, name)
            if isinstance(value, dict):
                value = kind(**mapping(value, kind.__dataclass_fields__, 'evidence.' + name))
                object.__setattr__(self, name, value)
            if not isinstance(value, kind):
                raise ValueError('invalid evidence.' + name)
            if name not in {'delegation', 'instructions', 'retention'} and any(type(v) is not int or v < 1 for v in asdict(value).values()):
                raise ValueError('evidence limits must be positive integers')
        if self.retention.enabled and not self.delegation.enabled:
            raise ValueError('incremental retention requires explicit delegation')
        if not self.read.default_characters <= self.read.max_characters <= 24000:
            raise ValueError('evidence read sizes require default <= maximum <= 24000')
        if not self.catalog.default_entries <= self.catalog.max_entries <= 100:
            raise ValueError('evidence catalog sizes require default <= maximum <= 100')
        if not self.search.default_matches <= self.search.max_matches <= 50 or self.search.max_characters > 24000:
            raise ValueError('invalid evidence search limits')

    @classmethod
    def from_dict(cls, value=None):
        if isinstance(value, cls):
            return value
        return cls(**mapping({} if value is None else value, cls.__dataclass_fields__, 'evidence'))

    def to_dict(self):
        return asdict(self)
