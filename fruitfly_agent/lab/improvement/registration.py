"""Shared parameter declarations and assembly for native text improvers."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, TYPE_CHECKING

from fruitfly_agent.core.mechanisms import ParameterDescriptor
from fruitfly_agent.lab.algorithms.targets import TEXT_TARGET_PREFIX
from fruitfly_agent.lab.improvement.runtime.host import HostedTextImprover
from fruitfly_agent.lab.improvement.tasks import TASK_PACK_COMPONENT
from fruitfly_agent.lab.improvement.api import TEXT_IMPROVER_COMPONENT, TEXT_IMPROVEMENT_TARGET_COMPONENT
from fruitfly_agent.lab.improvement.runtime.services import NativeSearchServices
from .trials import TRIAL_SERVICES_COMPONENT

if TYPE_CHECKING:
    from fruitfly_agent.lab.catalog.assembly import AssemblyContext, AssemblyState
    from fruitfly_agent.lab.improvement.contracts.search import Improver


def text_target_parameters() -> tuple[ParameterDescriptor, ...]:
    return (
        ParameterDescriptor("target", "string", "Text target", "Enabled named target.", "base_prompt"),
        ParameterDescriptor(
            "cases_path", "path", "Default task pack or legacy cases JSON",
            "Workspace-relative path; escaping the workspace is rejected.",
            ".fruitfly/improvement/cases.json",
        ),
    )


def text_budget_parameters() -> tuple[ParameterDescriptor, ...]:
    return (
        ParameterDescriptor("max_metric_calls", "integer", "Trial budget", "Root trial call limit.", 32, minimum=1, maximum=200),
        ParameterDescriptor("max_model_calls", "integer", "Model budget", "Root Provider attempt limit for all roles and trials.", 64, minimum=1, maximum=300),
        ParameterDescriptor("output_max_tokens", "integer", "Output limit", "Per request output token cap.", 1024, minimum=128, maximum=4096),
        ParameterDescriptor("call_timeout_seconds", "integer", "Call timeout", "Maximum seconds per operation.", 30, minimum=1, maximum=180),
    )


def install_text_improver(
    state: AssemblyState,
    context: AssemblyContext,
    parameters: Mapping[str, Any],
    *,
    strategy: Improver,
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
    improver = HostedTextImprover(
        strategy, state.config, context.workspace, parameters,
        target=state.components.get(TEXT_TARGET_PREFIX + parameters["target"]),
        label=label, role_configs=role_configs, task_source=source,
        services_factory=state.components.get(TRIAL_SERVICES_COMPONENT, NativeSearchServices),
    )
    context.own(improver)
    return (
        state.with_component(TEXT_IMPROVER_COMPONENT, improver)
        .with_component(TASK_PACK_COMPONENT, source)
        .with_component(TEXT_IMPROVEMENT_TARGET_COMPONENT, parameters["target"])
    )
