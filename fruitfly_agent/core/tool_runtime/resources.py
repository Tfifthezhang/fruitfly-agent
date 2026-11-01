"""Host-owned read-only resources; concrete routing belongs outside Core."""
from typing import Protocol


class ReadableResources(Protocol):
    def read(self, reference: str) -> bytes: ...
    def close(self) -> None: ...
