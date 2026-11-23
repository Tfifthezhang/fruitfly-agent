"""Owner workers produce changes through host-supplied durable call boundaries."""
from typing import Any, Awaitable, Callable, NamedTuple, Protocol, TypedDict


class MaintenanceRequest(TypedDict):
    operation: str
    request_id: str
    turns: int
    processed: int
    entries: list[dict[str, Any]]
    unchanged: bool
    manual: bool


class MaintenanceResult(NamedTuple):
    documents: str | None
    processed: int | None
    turns: int | None


class MaintenanceCall(Protocol):
    async def __call__(self, instructions: str, prompt: str,
                       generate: Callable[[], Awaitable[str]]) -> str: ...


class MaintenanceWorker(Protocol):
    library_id: str

    def request(self, checkpoint: dict, documents: str, *, manual: bool = False) -> MaintenanceRequest | None: ...

    async def generate(self, request: MaintenanceRequest, checkpoint: dict,
                       read_evidence: Callable, *, call: MaintenanceCall | None = None,
                       on_call: Callable[[], None] | None = None,
                       on_activity: Callable[..., Awaitable[None]] | None = None,
                       observed_at: str | None = None) -> MaintenanceResult: ...
