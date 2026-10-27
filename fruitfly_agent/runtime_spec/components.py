"""Serializable component instances, independent of algorithm factories."""
from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
import json
import re
from typing import Any, Mapping

from .documents import mapping

_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*')


@dataclass(frozen=True)
class ComponentConfiguration:
    id: str
    role: str
    implementation: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    enabled: bool = True
    source: str = field(default='', compare=False)
    reference: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)
    artifacts: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if any(not isinstance(v, str) or not _ID.fullmatch(v) for v in (self.id, self.implementation)):
            raise ValueError('component ID and implementation must be stable identifiers')
        if self.role not in {'H', 'S', 'I'} or type(self.enabled) is not bool:
            raise ValueError('component needs H/S/I role and boolean enabled')
        if not isinstance(self.parameters, Mapping):
            raise ValueError('component ' + self.id + ' parameters must be a mapping')
        # Reject opaque Python/YAML objects and nonfinite numbers before hashing.
        try:
            json.dumps(dict(self.parameters), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError('component parameters require finite JSON values') from exc
        object.__setattr__(self, 'parameters', deepcopy(dict(self.parameters)))
        if not isinstance(self.artifacts, Mapping) or any(not isinstance(k, str) or not k or not isinstance(v, str)
                for k, v in self.artifacts.items()):
            raise ValueError('component artifacts must map declared slots to exact text')
        object.__setattr__(self, 'artifacts', dict(self.artifacts))

    def to_dict(self):
        result = {'id': self.id, 'role': self.role,
                'implementation': self.implementation, 'enabled': self.enabled,
                'parameters': dict(self.parameters)}
        if self.artifacts:
            result['artifacts'] = dict(self.artifacts)
        return result

    @classmethod
    def from_dict(cls, value, *, source='', reference=None):
        mapping(value, {'id', 'role', 'implementation', 'enabled', 'parameters', 'artifacts'}, 'component')
        try:
            return cls(value['id'], value['role'], value['implementation'], value.get('parameters', {}),
                       value.get('enabled', True), source, reference or {}, value.get('artifacts', {}))
        except KeyError as exc:
            raise ValueError('component requires id, role and implementation') from exc
