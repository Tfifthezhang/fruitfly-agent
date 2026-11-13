"""Optional frontend capability for runtime-owned background operations."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OperationStatus:
    handle: str
    state: str
    elapsed_seconds: float
    run_id: str
    tool_call_id: str
    description: str = ''
    recent_output: str = ''


class OperationService(Protocol):
    def statuses(self) -> tuple[OperationStatus, ...]: ...
    def output(self, handle: str, *, offset: int = 0, limit: int = 12000) -> str: ...
    async def cancel(self, handle: str) -> OperationStatus: ...
