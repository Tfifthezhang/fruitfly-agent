"""Owned local and remote environment registration."""
from dataclasses import replace
from fruitfly_agent.runtime_spec.documents import parameter_default
from fruitfly_agent.lab.catalog.models import define_mechanism as _definition
from fruitfly_agent.lab.catalog.models import MechanismDefinition, ParameterDescriptor, MechanismEffects
from fruitfly_agent.lab.catalog.classification import OptimizationCoverage
from fruitfly_agent.lab.catalog.assembly import AssemblyState, AssemblyContext, require_workspace_path
from typing import Any, Mapping
from fruitfly_agent.lab.catalog.classification import ENVIRONMENT
from . import LocalEnv
from .description import EXECUTION_ENVIRONMENT_COMPONENT, ExecutionEnvironmentDescription
from .methods.remote.registration import definition as remote_definition


def definitions():
    return (_definition(
            "local-env",
            optimization_coverage=OptimizationCoverage('protected', 'Execution backend binding; tool and context owners expose optimization surfaces.'),
            layer="capability",
            family="environment",
            label="Local environment",
            description="Use the workspace filesystem and local shell.",
            install=_install_local_env,
            implementation_path='fruitfly_agent/lab/environment/methods/local/algorithm.py',
            documentation_path='fruitfly_agent/lab/environment/README.md',
            default=True,
            order=10,
            exclusive_group="environment",
            provides=frozenset({"execution-env"}),
            execution_description=lambda parameters, workspace: ExecutionEnvironmentDescription('Local', str(workspace)),
        feature_path=(ENVIRONMENT,),
), remote_definition())


def _install_local_env(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    backend = context.execution_env or LocalEnv(str(context.workspace))
    return replace(
        state,
        config=replace(state.config, env=backend),
    ).with_component(EXECUTION_ENVIRONMENT_COMPONENT,
        ExecutionEnvironmentDescription("Local", backend.cwd))
