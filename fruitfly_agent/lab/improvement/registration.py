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
            "Workspace-relative default source; selecting a saved task pack takes precedence. Escaping the workspace is rejected.",
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
    confirm_on_holdout=False,
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
        trial_targets=tuple(t for key, t in state.components.items()
                            if key.startswith(TEXT_TARGET_PREFIX) and getattr(t, 'project_in_trials', False)),
        confirm_on_holdout=confirm_on_holdout,
    )
    context.own(improver)
    return (
        state.with_component(TEXT_IMPROVER_COMPONENT, improver)
        .with_component(TASK_PACK_COMPONENT, source)
        .with_component(TEXT_IMPROVEMENT_TARGET_COMPONENT, parameters["target"])
    )


def native_method_definition(strategy_type, *, label, description, implementation_path, documentation_path,
                             family, target, parameters, direction_help=''):
    """Declare a native method with the shared on-demand text-artifact host."""
    from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects
    from fruitfly_agent.lab.catalog.models import MechanismDefinition
    from fruitfly_agent.lab.improvement.methods import MethodDefinition
    target_fields = tuple(replace(p, default=target) if p.name == 'target' else p
                          for p in text_target_parameters())
    def install(state, context, values):
        return install_text_improver(state, context, values, strategy=strategy_type(), label=label,
                                     roles=('improver', 'curriculum'), confirm_on_holdout=True)
    return MechanismDefinition(MechanismDescriptor(strategy_type.spec.algorithm_id, label,
        description,
        contributions=(MechanismContribution('improvement', 'context'),
                       *((MechanismContribution('improvement', family),) if family != 'context' else ())),
        parameters=(*target_fields, *text_budget_parameters(), *parameters),
        exclusive_group='text-improver', install_order=76,
        effects=MechanismEffects(uses_provider=True, uses_network=True, writes_files=True,
            cost_notice='Explicit search runs scored trials and model requests and stores evidence; calls may incur charges.')),
        install, implementation_id=strategy_type.spec.implementation_id,
        implementation_path=implementation_path, documentation_path=documentation_path,
        provides=frozenset({'text-improver'}), selection_group='text-improver', selection_group_label='Text improver',
        improvement=MethodDefinition(strategy_type.supported_roles, strategy_type.supported_schemas,
            strategy_type.required_capabilities | frozenset({'workflow-trials'}),
            lambda binding: binding.text_host(strategy_type(), label=label, confirm_on_holdout=True),
            usage=strategy_type.usage, budget_parameters=tuple(p.name for p in text_budget_parameters()),
            direction_help=direction_help, material_parameters=('cases_path',)))
