"""Strict shared evidence response limits, independent of editor/evaluator policy."""
from dataclasses import dataclass, field, asdict
from fruitfly_agent.runtime_spec.documents import mapping


@dataclass(frozen=True)
class ReadSettings:
    default_characters: int = 12000
    max_characters: int = 24000


@dataclass(frozen=True)
class CatalogSettings:
    default_entries: int = 50
    max_entries: int = 100


@dataclass(frozen=True)
class SearchSettings:
    default_matches: int = 20
    max_matches: int = 50
    max_characters: int = 12000


@dataclass(frozen=True)
class SupplySettings:
    max_characters: int = 256000
    max_pages: int = 64


@dataclass(frozen=True)
class EvidenceSettings:
    read: ReadSettings = field(default_factory=ReadSettings)
    catalog: CatalogSettings = field(default_factory=CatalogSettings)
    search: SearchSettings = field(default_factory=SearchSettings)
    supply: SupplySettings = field(default_factory=SupplySettings)

    def __post_init__(self):
        for name, kind in (('read', ReadSettings), ('catalog', CatalogSettings), ('search', SearchSettings), ('supply', SupplySettings)):
            value = getattr(self, name)
            if isinstance(value, dict):
                value = kind(**mapping(value, kind.__dataclass_fields__, 'evidence.' + name))
                object.__setattr__(self, name, value)
            if not isinstance(value, kind):
                raise ValueError('invalid evidence.' + name)
            if any(type(v) is not int or v < 1 for v in asdict(value).values()):
                raise ValueError('evidence limits must be positive integers')
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
