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
    run_loop: Callable[..., Awaitable[Any]] | None = None
    work_products: Any = None


class AgentRuntimeError(RuntimeError):
    """Bounded public admission category, separate from sensitive exception text."""
    def __init__(self, code: str):
        if not code or len(code) > 80 or any(c not in 'abcdefghijklmnopqrstuvwxyz_' for c in code):
            raise ValueError('invalid runtime admission category')
        self.code = code
        super().__init__(code)


def prepare_agent_config(config):
    """Supply isolated shared measurement for an independently hosted Core invocation."""
    from dataclasses import replace
    from fruitfly_agent.lab.context_manager.measurement import new_measurement_scope
    return replace(config, context_meter=new_measurement_scope(config.context_meter))
