"""Public tasks contracts; no external effects."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Protocol
from fruitfly_agent.improvement.contracts.validation import identifier, relative_path, bounded
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash, require_hash

@dataclass(frozen=True)
class Resource:
    path: str
    artifact_id: str
    media_type: str = 'text/plain; charset=utf-8'
    kind: str = 'input'

    def __post_init__(self):
        relative_path(self.path)
        require_hash(self.artifact_id)
        bounded(self.media_type, 200)
        if self.kind not in {'input', 'trajectory', 'deliverable', 'diagnostic'}:
            raise ValueError('invalid resource role')


@dataclass(frozen=True)
class TaskMaterial:
    task_id: str
    instruction: str
    inputs: tuple[Resource, ...] = ()
    environment_id: str = 'isolated-local'
    origin: str = 'interaction'

    def __post_init__(self):
        identifier(self.task_id)
        bounded(self.instruction)
        bounded(self.environment_id, 500)
        bounded(self.origin, 1000)
        object.__setattr__(self, 'inputs', tuple(self.inputs))
        if len({r.path for r in self.inputs}) != len(self.inputs):
            raise ValueError('task input paths must be distinct')

    @property
    def material_id(self):
        return content_hash(canonical_json(asdict(self)))


class ArtifactAccess(Protocol):
    def put(self, content: bytes) -> str: ...
    def read(self, artifact_id: str) -> bytes: ...


class TaskSource(Protocol):
    def freeze(self, task_id: str, instruction: str, *, paths=(),
               environment_id: str = 'isolated-local') -> TaskMaterial: ...



@dataclass(frozen=True)
class TaskCase:
    input: str
    expected: str
    verification: str = ""

    def __post_init__(self):
        if not isinstance(self.input, str) or not isinstance(self.expected, str):
            raise ValueError("case fields must be strings")
        if not self.input.strip() or not self.expected.strip():
            raise ValueError("case input and expected must not be empty")
        if not isinstance(self.verification, str) or len(self.verification) > 16000:
            raise ValueError("verification must be bounded immutable text")
        if len(self.input) > 4000 or len(self.expected) > 1000:
            raise ValueError("case exceeds the text size limit")

    @property
    def case_id(self):
        return content_hash(self.input + "\0" + self.expected + ("\0" + self.verification if self.verification else ""))

