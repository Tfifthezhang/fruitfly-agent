"""Assembly for the independent IPython tool and RLM externalization."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
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

IPYTHON_TOOL_PROMPT = """
## Persistent IPython workspace

This Session has an opt-in persistent IPython workspace. Use the `ipython`
tool for programmatic inspection, filtering, aggregation and verification.
Variables and imports persist across ipython calls while this Runtime is open.
Top-level `await` is supported.

Use the preloaded synchronous `context` object to manage artifacts:

- `context.list()` and `context.stat(reference)`
- `context.read(reference, offset=0, limit=20000)`
- `context.search(reference, query, limit=20)`
- `context.put(text)` for large intermediate text
- `context.save_state(name, json_value)` and `context.load_state(name)` for
  explicit state that must survive `/resume`

Do not print a whole large artifact merely to inspect it. Search or read
bounded slices and keep intermediate values in Python.

For semantic work that deterministic Python cannot perform, call the bounded,
text-only auxiliary model from IPython:

`reply = await llm_query(prompt, max_output_tokens=2048)`

The returned dict contains `text`, model identity, usage and an optional
`reference` when the full result was stored externally. Calls incur network
cost and have hard per-Runtime call/token/concurrency limits. The auxiliary
call has no tools and cannot recursively invoke `llm_query`.

The IPython process uses the current workspace permissions and is not a
security sandbox. Important resume state must be saved explicitly as JSON or
context artifacts; arbitrary live Python objects are not restored.
""".strip()

RLM_IPYTHON_PROMPT = """Large messages may be replaced in model context by a
`context://sha256/...` reference. The original content remains in the Session
artifact store. Use the `ipython` tool and its preloaded `context` object to
inspect referenced content in bounded slices."""


@dataclass(frozen=True)
class IpythonToolConfig:
    max_artifact_bytes: int = 64 * 1024 * 1024
    max_cell_output_chars: int = 50_000
    cell_timeout_seconds: int = 120
    max_query_calls: int = 16
    max_query_concurrent: int = 4
    max_query_input_chars: int = 200_000
    max_query_output_tokens: int = 4_096
    max_query_total_tokens: int = 100_000
    max_query_inline_result_chars: int = 100_000
    query_timeout_seconds: int = 180


@dataclass(frozen=True)
class RlmIpythonConfig:
    offload_threshold_chars: int = 50_000


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
    binding = context.provider_resolver(None, config.max_query_output_tokens)
    broker = ModelQueryBroker(
        binding.provider,
        model=binding.model,
        profile=binding.profile,
        store=store,
        config=ModelQueryConfig(
            max_calls=config.max_query_calls,
            max_concurrent=config.max_query_concurrent,
            max_input_chars=config.max_query_input_chars,
            max_output_tokens=config.max_query_output_tokens,
            max_total_tokens=config.max_query_total_tokens,
            max_inline_result_chars=config.max_query_inline_result_chars,
            timeout_seconds=config.query_timeout_seconds,
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
    )
    prompt = state.config.system_prompt
    prompt = f"{prompt}\n\n{IPYTHON_TOOL_PROMPT}" if prompt else IPYTHON_TOOL_PROMPT
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
    prompt = f"{prompt}\n\n{RLM_IPYTHON_PROMPT}" if prompt else RLM_IPYTHON_PROMPT
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
    "IPYTHON_TOOL_PROMPT",
    "IpythonToolConfig",
    "RLM_IPYTHON_PROMPT",
    "RlmIpythonComponent",
    "RlmIpythonConfig",
    "install_ipython_tool",
    "install_rlm_ipython",
]
