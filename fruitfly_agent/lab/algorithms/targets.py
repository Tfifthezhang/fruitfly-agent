"""Named text targets expose validation and host binding instructions."""
from dataclasses import dataclass, asdict
import hashlib
import json
import re
from typing import Literal, Protocol, runtime_checkable
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.improvement.contracts.versions import (SystemVersion, StateSnapshot, SnapshotFile, STATE_SNAPSHOTS_COMPONENT, EXPERIMENT_BLOCKERS_COMPONENT,
                       canonical_json, content_hash)
from fruitfly_agent.improvement.contracts.candidates import VersionCandidate, TargetChange, TargetRegistry

TEXT_TARGET_PREFIX = 'text-target:'


def state_artifact_path(key):
    """Stable virtual snapshot location for a registered retained-text binding."""
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', key):
        raise ValueError('state artifact key must be a stable identifier')
    return f'.fruitfly/retained/{key}/document.md'


@dataclass(frozen=True)
class TargetBinding:
    kind: Literal['prompt', 'artifact', 'components', 'configuration']
    key: str = ''

    def __post_init__(self):
        if self.kind not in {'prompt', 'artifact', 'components', 'configuration'} or (self.kind in {'artifact', 'configuration'} and not self.key):
            raise ValueError('invalid target binding')


@dataclass(frozen=True)
class TargetSnapshot:
    target_id: str
    text: str
    binding: TargetBinding
    schema: str = 'text-v1'
    role: str = 'H'
    components: tuple['TargetSnapshot', ...] = ()

    def __post_init__(self):
        if self.role not in {'H', 'S', 'I'}:
            raise ValueError('target role must be H, S or I')
        if not isinstance(self.target_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', self.target_id):
            raise ValueError('target identity must be a stable identifier')
        if not isinstance(self.text, str) or not isinstance(self.binding, TargetBinding):
            raise TypeError('target requires text and a typed binding')
        object.__setattr__(self, 'components', tuple(self.components))
        if self.binding.kind == 'components':
            if (not self.components or any(p.components for p in self.components)
                    or len({p.target_id for p in self.components}) != len(self.components)
                    or len({p.binding for p in self.components}) != len(self.components)):
                raise ValueError('component targets need distinct flat registered bindings')
        elif self.components:
            raise ValueError('only a component binding can contain component snapshots')

    @property
    def content_hash(self):
        return 'sha256:' + hashlib.sha256(self.text.encode('utf-8')).hexdigest()

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or set(data) != set(cls.__dataclass_fields__):
            raise ValueError('invalid target snapshot')
        return cls(**{**data, 'binding': TargetBinding(**data['binding']),
                      'components': tuple(cls.from_dict(p) for p in data['components'])})


@runtime_checkable
class TextTarget(Protocol):
    def snapshot(self) -> TargetSnapshot: ...
    def validate(self, text: str) -> None: ...
    def prepare_trial(self, config: AgentLoopConfig, text: str) -> AgentLoopConfig: ...


def validate_text(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 30_000:
        raise ValueError('candidate text must contain 1–30,000 characters')
    if any(ord(char) < 32 and char not in '\n\t' for char in text):
        raise ValueError('candidate text contains control characters')


def expand_target(snapshot, text):
    """Resolve a complete component document without knowing any concrete object."""
    if snapshot.binding.kind != 'components':
        validate_text(text)
        return ((snapshot, text),)
    if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > 2_000_000:
        raise ValueError('component document exceeds its 2MB allocation')
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError('component candidate must be a JSON object') from exc
    if (not isinstance(data, dict) or set(data) != {p.target_id for p in snapshot.components}
            or canonical_json(data) != text):
        raise ValueError('component candidate must contain exactly the registered IDs as canonical JSON')
    result = tuple((part, data[part.target_id]) for part in snapshot.components)
    for part, value in result:
        if not isinstance(value, str):
            raise ValueError('component values must be instruction text')
    return result


def target_edits(snapshot, text):
    """Return only changed leaves; unchanged components retain their bindings."""
    return tuple((part, value) for part, value in expand_target(snapshot, text) if part.text != value)
