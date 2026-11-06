"""Owned programmatic-context registration."""
from dataclasses import replace
from fruitfly_agent.runtime_spec.documents import parameter_default
from fruitfly_agent.lab.catalog.models import define_mechanism as _definition
from fruitfly_agent.lab.catalog.models import MechanismDefinition, ParameterDescriptor, MechanismEffects
from fruitfly_agent.lab.catalog.classification import OptimizationCoverage
from fruitfly_agent.lab.catalog.assembly import AssemblyState, AssemblyContext, require_workspace_path
from typing import Any, Mapping
from fruitfly_agent.lab.catalog.classification import CONTEXT, EXTERNALIZATION
from fruitfly_agent.lab.catalog.adapters.parameters import editable_parameters
from .methods.programmatic_context.algorithm import RlmIpythonConfig, install_rlm_ipython


def definitions():
    return (editable_parameters(_definition(
            "rlm-ipython",
            layer="online",
            family="context",
            context_phase="externalization",
            label="Programmatic Context (RLM)",
            selection_group="externalization",
            selection_group_label="Externalization",
            exclusive_group="externalization",
            description=(
                "Externalize large context for inspection through the IPython tool."
            ),
            install=install_rlm_ipython,
            validate_parameters=lambda values: RlmIpythonConfig(**values),
            implementation_path='fruitfly_agent/lab/context_manager/externalization/methods/programmatic_context/algorithm.py',
            documentation_path='fruitfly_agent/lab/context_manager/externalization/methods/programmatic_context/README.md',
            requires=frozenset({"ipython-tool"}),
            order=65,
            parameters=(
                ParameterDescriptor(
                    "offload_threshold_chars", "integer", "Offload threshold",
                    "Minimum characters before content is stored as an artifact.",
                    parameter_default('fruitfly_agent.lab.context_manager.externalization.methods.programmatic_context', 'defaults.yaml', 'settings.offload_threshold_chars'),
                    minimum=1, advanced=True,
                ),
                ParameterDescriptor('usage_instructions', 'string', 'Reference guidance',
                    'How to read externalized context references.', RlmIpythonConfig().usage_instructions),
            ),
            effects=MechanismEffects(
                writes_files=True,
            ),
            default_resource=('fruitfly_agent.lab.context_manager.externalization.methods.programmatic_context', 'defaults.yaml'),
            parameter_paths={'offload_threshold_chars': 'settings.offload_threshold_chars',
                             'usage_instructions': 'instructions.usage'},
        feature_path=(CONTEXT, EXTERNALIZATION),
), {'offload_threshold_chars', 'usage_instructions'}),)
