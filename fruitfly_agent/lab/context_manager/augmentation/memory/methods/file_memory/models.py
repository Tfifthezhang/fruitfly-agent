"""Cross-session memory values; no storage, model construction or activation."""
from dataclasses import dataclass

KINDS = ('profile', 'preference', 'feedback', 'project', 'reference')
MUTABLE = frozenset({'description', 'body', 'applicability'})


@dataclass(frozen=True)
class MemoryEvidence:
    session_id: str
    message_id: str
    text: str
    completed: bool

    @property
    def identity(self):
        return self.session_id + ':' + self.message_id
