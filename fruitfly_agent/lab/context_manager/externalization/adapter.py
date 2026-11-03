"""Assembly for the independent IPython tool and RLM externalization."""

from __future__ import annotations

from dataclasses import dataclass, replace, field
from pathlib import Path
from fruitfly_agent.runtime_spec.documents import parameter_default
from typing import Any, Mapping

from fruitfly_agent.lab.tools import create_ipython_tool
from .programmatic_context.protocols import ContextArtifactWriter

from fruitfly_agent.lab.context_manager.externalization.programmatic_context.artifacts import SessionArtifactStore
from fruitfly_agent.core.context import ContextStage

from fruitfly_agent.lab.context_manager.externalization.programmatic_context.projection import (
    ProgrammaticContextExternalizer,
)
from fruitfly_agent.lab.context_manager.externalization.programmatic_context.query import (
    ModelQueryBroker,
    ModelQueryConfig,
)
from fruitfly_agent.lab.context_manager.externalization.programmatic_context.runtime import IpythonRuntime

CONTEXT_ARTIFACT_STORE = "context-artifact-store"






@dataclass(frozen=True)
class IpythonToolConfig:
    query_model_profile: str = ""
    max_artifact_bytes: int = field(default_factory=lambda: parameter_default(__package__, 'ipython-tool.yaml', 'settings.max_artifact_bytes'))
    max_cell_output_chars: int = field(default_factory=lambda: parameter_default(__package__, 'ipython-tool.yaml', 'settings.max_cell_output_chars'))
    cell_timeout_seconds: int = field(default_factory=lambda: parameter_default(__package__, 'ipython-tool.yaml', 'settings.cell_timeout_seconds'))
    max_query_concurrent: int = field(default_factory=lambda: parameter_default(__package__, 'ipython-tool.yaml', 'settings.max_query_concurrent'))
    max_query_input_chars: int = field(default_factory=lambda: parameter_default(__package__, 'ipython-tool.yaml', 'settings.max_query_input_chars'))
    max_query_output_tokens: int = field(default_factory=lambda: parameter_default(__package__, 'ipython-tool.yaml', 'settings.max_query_output_tokens'))
    max_query_inline_result_chars: int = field(default_factory=lambda: parameter_default(__package__, 'ipython-tool.yaml', 'settings.max_query_inline_result_chars'))
    query_timeout_seconds: int = field(default_factory=lambda: parameter_default(__package__, 'ipython-tool.yaml', 'settings.query_timeout_seconds'))
    usage_instructions: str = field(default_factory=lambda: parameter_default(__package__, 'ipython-tool.yaml', 'instructions.usage'))
    query_instructions: str = field(default_factory=lambda: parameter_default(__package__, 'ipython-tool.yaml', 'instructions.query'))

    def __post_init__(self):
        for value in (self.usage_instructions, self.query_instructions):
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 12000:
                raise ValueError('IPython instructions must contain 1..12000 characters')


@dataclass(frozen=True)
class RlmIpythonConfig:
    offload_threshold_chars: int = field(default_factory=lambda: parameter_default(__package__, 'rlm-ipython.yaml', 'settings.offload_threshold_chars'))
    usage_instructions: str = field(default_factory=lambda: parameter_default(__package__, 'rlm-ipython.yaml', 'instructions.usage'))

    def __post_init__(self):
        if not isinstance(self.usage_instructions, str) or not 1 <= len(self.usage_instructions.strip()) <= 12000:
            raise ValueError('RLM instructions must contain 1..12000 characters')


class RlmIpythonComponent:
    def __init__(self, runtime: IpythonRuntime, broker: ModelQueryBroker) -> None:
        self.runtime = runtime
        self.broker = broker

    async def start(self) -> None:
        await self.runtime.start()

    async def health(self) -> dict[str, Any]:
        return {
            "runtime": await self.runtime.health(),
            "model_query": await self.broker.health(),
        }

    async def close(self) -> None:
        await self.runtime.close()


def install_ipython_tool(
    state: Any,
    context: Any,
    parameters: Mapping[str, Any],
) -> Any:
    """Install a persistent IPython workspace and bounded model queries."""

    config = IpythonToolConfig(**parameters)
    if context.session_path is None:
        raise ValueError("ipython-tool requires a persistent Session path")
    artifact_root = _artifact_root(context.session_path)
    store = SessionArtifactStore(
        artifact_root,
        max_artifact_bytes=config.max_artifact_bytes,
    )
    binding = context.provider_for_role('context_query', config.max_query_output_tokens)
    broker = ModelQueryBroker(
        binding.provider,
        model=binding.model,
        profile=binding.profile,
        store=store,
        config=ModelQueryConfig(
            max_concurrent=config.max_query_concurrent,
            max_input_chars=config.max_query_input_chars,
            max_output_tokens=config.max_query_output_tokens,
            max_inline_result_chars=config.max_query_inline_result_chars,
            timeout_seconds=config.query_timeout_seconds,
            instructions=config.query_instructions,
        ),
    )

    async def handle(request_type, payload, signal):
        return await broker.handle(request_type, payload, signal=signal)

    runtime = IpythonRuntime(
        cwd=context.workspace,
        artifact_store=store,
        host_handler=handle,
        max_output_chars=config.max_cell_output_chars,
        timeout_seconds=config.cell_timeout_seconds,
        process_environment=dict(context.process_environment) if context.process_environment is not None else None,
    )
    prompt = state.config.system_prompt
    prompt = f"{prompt}\n\n{config.usage_instructions}" if prompt else config.usage_instructions
    assembled = replace(
        state,
        config=replace(
            state.config,
            system_prompt=prompt,
            tools=(*state.config.tools, create_ipython_tool(runtime)),
        ),
    )
    component = context.own(RlmIpythonComponent(runtime, broker))
    return assembled.with_component("ipython-tool", component).with_component(CONTEXT_ARTIFACT_STORE, store)


def install_rlm_ipython(
    state: Any,
    context: Any,
    parameters: Mapping[str, Any],
) -> Any:
    """Externalize large context using the already installed IPython store."""
    store = state.components.get(CONTEXT_ARTIFACT_STORE)
    if not isinstance(store, ContextArtifactWriter):
        raise ValueError("rlm-ipython requires a context artifact store")
    externalizer = ProgrammaticContextExternalizer(
        store,
        threshold_chars=parameters["offload_threshold_chars"],
    )
    prompt = state.config.system_prompt
    usage = parameters["usage_instructions"]
    prompt = f"{prompt}\n\n{usage}" if prompt else usage
    assembled = replace(state, config=replace(state.config, system_prompt=prompt))
    return assembled.with_context_stage(
        ContextStage(
            "rlm-ipython",
            "externalization",
            externalizer,
            order=65,
        )
    )


def _artifact_root(session_path: Path) -> Path:
    return session_path.with_suffix(session_path.suffix + ".artifacts") / "rlm"


__all__ = [
    "IpythonToolConfig",
    "RlmIpythonComponent",
    "RlmIpythonConfig",
    "install_ipython_tool",
    "install_rlm_ipython",
]
