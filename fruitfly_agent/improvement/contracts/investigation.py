"""Evidence selection is a research decision, separate from task execution."""
from typing import Protocol


class EvidenceSelector(Protocol):
    @property
    def identity(self) -> str: ...

    def select(self, summaries: tuple[dict, ...], *, resources=None) -> dict:
        """Return selected run identities, reasons and explicit coverage limits."""
        ...
