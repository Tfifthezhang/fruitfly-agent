"""Source-attributed evidence access shared by editors and evaluators."""
from dataclasses import asdict, dataclass
from typing import Protocol

from .versions import canonical_json, content_hash, require_hash


@dataclass(frozen=True)
class EvidenceSpan:
    artifact_id: str
    start: int
    end: int

    def __post_init__(self):
        require_hash(self.artifact_id)
        if type(self.start) is not int or type(self.end) is not int or not 0 <= self.start <= self.end:
            raise ValueError('evidence spans need an ordered source character interval')

    @property
    def citation_id(self):
        return content_hash(canonical_json(asdict(self)))


class EvidenceReader(Protocol):
    def catalog(self, *, prefix: str = '', cursor: int = 0, limit: int = 50) -> dict: ...
    def search(self, query: str, *, paths: tuple[str, ...] = (), cursor: str = '', limit: int = 20) -> dict: ...
    def read(self, path: str, *, offset: int = 0, limit: int = 12000) -> dict: ...
