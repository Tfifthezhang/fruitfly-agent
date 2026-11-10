"""Read-only, immutable views of host-managed child executions."""
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class SubagentStatus:
    agent_id: str
    run_id: str
    task: str
    state: str
    cleanup: str
    model: str
    model_profile: str
    activity: str
    created_at: float
    started_at: float | None
    ended_at: float | None
    elapsed_seconds: float | None
    model_requests: int
    tool_calls: int
    input_tokens: int | None
    output_tokens: int | None
    summary: str
    error: str | None
    result_reference: str | None

@dataclass(frozen=True)
class SubagentSnapshot:
    revision: int
    max_concurrent: int
    executions: tuple[SubagentStatus, ...]
    poisoned: bool = False

class SubagentMonitor(Protocol):
    def snapshot(self) -> SubagentSnapshot: ...
    def detail(self, agent_id: str, run_id: str | None = None) -> SubagentStatus: ...
