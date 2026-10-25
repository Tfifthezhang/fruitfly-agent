"""Typed changes are independent of the algorithm that generated them."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Protocol
from fruitfly_agent.lab.improvement.contracts.versions import SystemVersion, canonical_json, content_hash, require_hash


@dataclass(frozen=True)
class TargetChange:
    role: str
    target_id: str
    schema: str
    before: str
    after: str

    def __post_init__(self) -> None:
        if self.role not in {"H", "I", "S"}:
            raise ValueError("target change role must be H, I or S")
        if any(not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", v)
               for v in (self.target_id, self.schema)):
            raise ValueError("target and content schema must be stable identifiers")
        require_hash(self.before)
        require_hash(self.after)
        if self.before == self.after:
            raise ValueError("a candidate must change target content")


@dataclass(frozen=True)
class VersionCandidate:
    parent: SystemVersion
    version: SystemVersion
    changes: tuple[TargetChange, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "changes", tuple(self.changes))
        if not self.changes or len({(c.role, c.target_id) for c in self.changes}) != len(self.changes):
            raise ValueError("candidate needs distinct declared target changes")
        roles = {c.role for c in self.changes}
        for role, field in (("H", "harness"), ("I", "improver"), ("S", "state")):
            changed = getattr(self.parent, field) != getattr(self.version, field)
            if changed != (role in roles):
                raise ValueError("candidate version differs from its declared modification scope")

    @property
    def candidate_id(self) -> str:
        return content_hash(canonical_json(self.to_dict()))

    def to_dict(self) -> dict:
        return {"parent": self.parent.to_dict(), "version": self.version.to_dict(),
                "changes": [asdict(c) for c in self.changes]}

    @classmethod
    def from_dict(cls, data: dict) -> VersionCandidate:
        if not isinstance(data, dict) or set(data) != {"parent", "version", "changes"}:
            raise ValueError("invalid version candidate")
        return cls(SystemVersion.from_dict(data["parent"]), SystemVersion.from_dict(data["version"]),
                   tuple(TargetChange(**c) for c in data["changes"]))


class ChangeAdapter(Protocol):
    def validate_change(self, change: TargetChange) -> None: ...


class TargetRegistry:
    """Only explicitly registered role/target/schema combinations can execute."""
    def __init__(self) -> None:
        self.adapters: dict[tuple[str, str, str], ChangeAdapter] = {}

    def register(self, role: str, target_id: str, schema: str, adapter: ChangeAdapter) -> None:
        key = (role, target_id, schema)
        if role not in {"H", "I", "S"} or key in self.adapters:
            raise ValueError("invalid or duplicate target registration")
        self.adapters[key] = adapter

    def resolve(self, change: TargetChange) -> ChangeAdapter:
        try:
            return self.adapters[(change.role, change.target_id, change.schema)]
        except KeyError as exc:
            raise ValueError("unsupported improvement target: " + "/".join((change.role, change.target_id, change.schema))) from exc

    def validate(self, candidate: VersionCandidate, parent: SystemVersion) -> None:
        if candidate.parent != parent:
            raise ValueError("candidate parent H/I/S version is stale")
        for change in candidate.changes:
            adapter = self.resolve(change)
            adapter.validate_change(change)


from .components import HarnessSnapshot
from .validation import identifier, bounded

@dataclass(frozen=True)
class EditReason:
    component_id: str
    explanation: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self):
        identifier(self.component_id)
        bounded(self.explanation, 4000)
        object.__setattr__(self, 'evidence_ids', tuple(self.evidence_ids))
        if not self.evidence_ids or any(not isinstance(v, str) or not v for v in self.evidence_ids):
            raise ValueError('edits need attributable evidence')


@dataclass(frozen=True)
class CandidateBundle:
    parent: SystemVersion
    base: HarnessSnapshot
    harness: HarnessSnapshot
    generator_id: str
    reasons: tuple[EditReason, ...] = ()

    def __post_init__(self):
        identifier(self.generator_id)
        object.__setattr__(self, 'reasons', tuple(self.reasons))
        if {c.component_id for c in self.base.components} != {c.component_id for c in self.harness.components}:
            raise ValueError('candidates must preserve the registered component set')
        for c in self.harness.components:
            old = self.base.component(c.component_id)
            if (c.kind, c.role, c.schema) != (old.kind, old.role, old.schema):
                raise ValueError('candidates cannot change component ownership or schema')

    @property
    def changed_ids(self):
        return tuple(c.component_id for c in self.harness.components if c != self.base.component(c.component_id))

    @property
    def changed_roles(self):
        return frozenset(self.harness.component(v).role for v in self.changed_ids)

    @property
    def candidate_id(self):
        return content_hash(canonical_json(asdict(self)))

