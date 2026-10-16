"""Optional observation capability; material algorithms remain host-owned."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CompletedTask:
    source_id: str
    input: str
    output: str
    outcome: str
    manifest: str
    session: str


class LearningService(Protocol):
    async def observe(self, task: CompletedTask) -> bool: ...
