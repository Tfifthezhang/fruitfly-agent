"""Pure evidence views over already granted text; originals remain immutable."""
from dataclasses import dataclass
from typing import Callable

from fruitfly_agent.improvement.contracts.validation import identifier


@dataclass(frozen=True)
class EvidenceProjection:
    projection_id: str
    implementation_id: str
    render: Callable[[str, int, int], str]


class EvidenceProjectionRegistry:
    def __init__(self, definitions=()):
        self.entries: dict[str, EvidenceProjection] = {}
        for definition in definitions:
            identifier(definition.projection_id)
            identifier(definition.implementation_id)
            if definition.projection_id in self.entries or not callable(definition.render):
                raise ValueError('invalid or duplicate evidence projection')
            self.entries[definition.projection_id] = definition

    def get(self, name):
        try:
            return self.entries[name]
        except KeyError as exc:
            raise ValueError('unknown evidence projection: ' + str(name)) from exc

    def definitions(self):
        return tuple(self.entries.values())


def builtin_evidence_projections():
    return EvidenceProjectionRegistry((EvidenceProjection('granted-full', 'granted-text-page-v1',
        lambda text, offset, limit: text[offset:offset + limit]),))
