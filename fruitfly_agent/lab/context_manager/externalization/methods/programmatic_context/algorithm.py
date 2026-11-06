"""Externalize context through an injected artifact writer."""
from dataclasses import dataclass, replace, field
from typing import Any, Mapping
from fruitfly_agent.runtime_spec.documents import parameter_default
from fruitfly_agent.core.context import ContextStage
from fruitfly_agent.lab.context_manager.resources.artifacts import ContextArtifactWriter, CONTEXT_ARTIFACT_STORE
from .projection import ProgrammaticContextExternalizer

@dataclass(frozen=True)
class RlmIpythonConfig:
    offload_threshold_chars: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'settings.offload_threshold_chars'))
    usage_instructions: str = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'instructions.usage'))

    def __post_init__(self):
        if not isinstance(self.usage_instructions, str) or not 1 <= len(self.usage_instructions.strip()) <= 12000:
            raise ValueError('RLM instructions must contain 1..12000 characters')

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
