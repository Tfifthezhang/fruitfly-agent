"""Minimal artifact-writing capability required by context externalization."""
from typing import Protocol, runtime_checkable


class ContextArtifact(Protocol):
    reference: str
    characters: int
    size_bytes: int


@runtime_checkable
class ContextArtifactWriter(Protocol):
    def put_text(self, text: str, *, kind: str, origin: str) -> ContextArtifact: ...
