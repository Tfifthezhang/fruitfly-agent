"""OPRO-owned Catalog definition, parameters, effects, and installer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fruitfly_agent.core.mechanisms import (
    MechanismContribution, MechanismDescriptor, MechanismEffects, ParameterDescriptor,
)
from fruitfly_agent.lab.improvement.registration import install_text_improver, text_budget_parameters, text_target_parameters
from fruitfly_agent.lab.improvement.methods.opro.improver import OproImprover
from fruitfly_agent.lab.improvement.methods import MethodDefinition

if TYPE_CHECKING:
    from fruitfly_agent.lab.catalog.models import MechanismDefinition


def definition() -> MechanismDefinition:
    """Return a fresh definition; construction performs no search or model calls."""
    # Resolve the Catalog value when requested, so importing the method does not
    # import the built-in composition root that also collects this definition.
    from fruitfly_agent.lab.catalog.models import MechanismDefinition

    return MechanismDefinition(
        MechanismDescriptor(
            mechanism_id=OproImprover.spec.algorithm_id,
            label="OPRO",
            description="Generate instruction candidates from previously scored solutions and training feedback.",
            contributions=(MechanismContribution("improvement", "context"),),
            parameters=(
                *text_target_parameters(),
                ParameterDescriptor("rounds", "integer", "Search rounds", "Maximum bounded rounds.", 2, minimum=1, maximum=20),
                ParameterDescriptor("history_limit", "integer", "History view", "Maximum attempts included in generation context.", 5, minimum=1, maximum=20),
                *text_budget_parameters(),
                ParameterDescriptor("improver_profile", "string", "Improver model", "Optional model profile; empty uses the active Provider.", ""),
                ParameterDescriptor("batch_size", "integer", "Proposal batch", "Maximum proposals per round.", 2, minimum=1, maximum=5),
            ),
            exclusive_group="text-improver",
            install_order=76,
            effects=MechanismEffects(
                uses_provider=True, uses_network=True, writes_files=True,
                cost_notice="Explicit search invokes the configured Provider and stores research history; calls may incur charges.",
            ),
        ),
        _install,
        implementation_id=OproImprover.spec.implementation_id,
        implementation_path='fruitfly_agent/lab/improvement/methods/opro/improver.py',
        documentation_path='fruitfly_agent/lab/improvement/methods/opro/README.md',
        improvement=MethodDefinition(OproImprover.supported_roles, OproImprover.supported_schemas,
            OproImprover.required_capabilities, _bind, usage=OproImprover.usage,
            budget_parameters=tuple(p.name for p in text_budget_parameters()),
            direction_help='Optional guidance for proposing text candidates. Task scores determine candidate ranking.',
            material_parameters=('cases_path',)),
        provides=frozenset({"text-improver"}),
        selection_group="text-improver",
        selection_group_label="Text improver",
    )


def _install(state, context, parameters):
    return install_text_improver(
        state, context, parameters,
        strategy=OproImprover(), label="OPRO", roles=("improver",),
    )


def _bind(binding):
    return binding.text_host(OproImprover(), label="OPRO")
