"""Failure preparation has its own Catalog choice, separate from search methods."""
from dataclasses import replace

from fruitfly_agent.core.mechanisms import MechanismContribution, MechanismDescriptor, MechanismEffects, ParameterDescriptor
from .processors import ReplayFailureProcessor, ModelDistillationProcessor

FAILURE_PROCESSOR_COMPONENT = "improvement-failure-processor"
FAILURE_ROLES_COMPONENT = "improvement-failure-roles"


def definitions():
    from fruitfly_agent.lab.catalog.models import MechanismDefinition
    result = []
    for name, label, implementation, install, parameters, uses_provider in (
        ("failure-replay", "Retain failed tasks", ReplayFailureProcessor.implementation_id, _replay, (), False),
        ("failure-distillation", "Generate learning exercises", ModelDistillationProcessor.implementation_id, _distill,
         (ParameterDescriptor("materializer_profile", "string", "Material generator model", "Empty reuses the active Provider.", ""),
          ParameterDescriptor("material_reviewer_profile", "string", "Material reviewer model", "Empty reuses the active Provider.", "")), True),
    ):
        result.append(MechanismDefinition(
            MechanismDescriptor(name, label, "Prepare learning material from scored training failures.",
                contributions=(MechanismContribution("improvement", "context"),),
                parameters=parameters, install_order=74, exclusive_group="failure-processing",
                effects=MechanismEffects(uses_provider=uses_provider, uses_network=uses_provider,
                    cost_notice="Material generation and model review may incur charges." if uses_provider else "No material-generation model calls.")),
            install, implementation_id=implementation, provides=frozenset({"failure-processing"}),
            selection_group="failure-processing", selection_group_label="Failure processing"))
    return tuple(result)


def _replay(state, context, parameters):
    return state.with_component(FAILURE_PROCESSOR_COMPONENT, ReplayFailureProcessor())


def _distill(state, context, parameters):
    roles = {}
    for role in ("materializer", "material_reviewer"):
        profile = parameters[role + "_profile"]
        if profile:
            binding = context.provider_resolver(profile, None)
            roles[role] = replace(state.config, provider=binding.provider, model=binding.model,
                context_window=binding.context_window or state.config.context_window,
                max_tokens=binding.max_output_tokens or state.config.max_tokens)
    return (state.with_component(FAILURE_PROCESSOR_COMPONENT, ModelDistillationProcessor())
            .with_component(FAILURE_ROLES_COMPONENT, roles))
