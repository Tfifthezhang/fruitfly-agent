"""Host-prepared independent Agent resources, borrowed by execution services."""
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.context import ContextPipeline

@dataclass(frozen=True)
class PreparedAgentRuntime:
    config: AgentLoopConfig
    context_pipeline: ContextPipeline | None
    manifest: Mapping[str, Any]
    start: Callable[[], Awaitable[None]]
    close: Callable[[], Awaitable[None]]


class AgentRuntimeError(RuntimeError):
    """Bounded public admission category, separate from sensitive exception text."""
    def __init__(self, code: str):
        if not code or len(code) > 80 or any(c not in 'abcdefghijklmnopqrstuvwxyz_' for c in code):
            raise ValueError('invalid runtime admission category')
        self.code = code
        super().__init__(code)
