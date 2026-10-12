"""Shared parameter declarations and assembly for native text optimizers."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, TYPE_CHECKING

from fruitfly_agent.core.mechanisms import ParameterDescriptor
from fruitfly_agent.lab.algorithms.targets import TEXT_TARGET_PREFIX
from .host import HostedTextOptimizer
from .task_packs import TASK_PACK_COMPONENT
from .text_optimizer import TEXT_OPTIMIZER_COMPONENT, TEXT_OPTIMIZATION_TARGET_COMPONENT

if TYPE_CHECKING:
    from fruitfly_agent.lab.catalog.assembly import AssemblyContext, AssemblyState
    from .search import Optimizer


def text_target_parameters() -> tuple[ParameterDescriptor, ...]:
    return (
        ParameterDescriptor("target", "string", "Text target", "Enabled named target.", "base_prompt"),
        ParameterDescriptor(
            "cases_path", "path", "Default task pack or legacy cases JSON",
            "Workspace-relative path; escaping the workspace is rejected.",
            ".fruitfly/optimization/cases.json",
        ),
    )


def text_budget_parameters() -> tuple[ParameterDescriptor, ...]:
    return (
        ParameterDescriptor("max_metric_calls", "integer", "Trial budget", "Root trial call limit.", 32, minimum=1, maximum=200),
        ParameterDescriptor("max_model_calls", "integer", "Model budget", "Root Provider attempt limit for all roles and trials.", 64, minimum=1, maximum=300),
        ParameterDescriptor("output_max_tokens", "integer", "Output limit", "Per request output token cap.", 1024, minimum=128, maximum=4096),
        ParameterDescriptor("call_timeout_seconds", "integer", "Call timeout", "Maximum seconds per operation.", 30, minimum=1, maximum=180),
    )


def install_text_optimizer(
    state: AssemblyState,
    context: AssemblyContext,
    parameters: Mapping[str, Any],
    *,
    strategy: Optimizer,
    label: str,
    roles: tuple[str, ...],
) -> AssemblyState:
    """Bind an injected strategy without starting a search or calling a model."""
    source = state.components[TASK_PACK_COMPONENT].with_legacy(parameters["cases_path"])
    role_configs = {}
    for role in roles:
        profile = parameters.get(role + "_profile")
        if profile:
            binding = context.provider_resolver(profile, parameters["output_max_tokens"])
            role_configs[role] = replace(
                state.config, provider=binding.provider, model=binding.model,
                context_window=binding.context_window or state.config.context_window,
                max_tokens=binding.max_output_tokens or state.config.max_tokens,
            )
    optimizer = HostedTextOptimizer(
        strategy, state.config, context.workspace, parameters,
        target=state.components.get(TEXT_TARGET_PREFIX + parameters["target"]),
        label=label, role_configs=role_configs, task_source=source,
    )
    context.own(optimizer)
    return (
        state.with_component(TEXT_OPTIMIZER_COMPONENT, optimizer)
        .with_component(TASK_PACK_COMPONENT, source)
        .with_component(TEXT_OPTIMIZATION_TARGET_COMPONENT, parameters["target"])
    )
