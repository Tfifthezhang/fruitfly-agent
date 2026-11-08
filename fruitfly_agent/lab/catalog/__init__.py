"""Public catalog/profile/assembly API for selectable Lab mechanisms."""

from .assembly import (
    AssemblyContext,
    AssemblyResult,
    AssemblyState,
    ArtifactReader,
    ProviderBinding,
    ProviderResolver,
    assemble_lab,
    require_workspace_path,
)
from .catalog import LabCatalog
from .tool_providers import (PreparedToolProvider, ToolProviderContext, ToolServiceInfo,
                             ToolServiceStart, ProviderToolAuthorizer)
from fruitfly_agent.lab.environment.description import EXECUTION_ENVIRONMENT_COMPONENT, ExecutionEnvironmentDescription
from .models import (
    ActivationScope,
    ContextPhase,
    MechanismFamily,
    MechanismLayer,
    MechanismContribution,
    MechanismDefinition,
    MechanismDescriptor,
    MechanismEffects,
    MechanismInstaller,
    MechanismSelection,
    ParameterDescriptor,
    ParameterKind,
    ResolvedMechanism,
)


__all__ = [
    "PreparedToolProvider", "ToolProviderContext", "ToolServiceInfo", "ToolServiceStart", "ProviderToolAuthorizer",
    "ComponentSpec", "ResolvedHarness", "resolve_harness", "verify_runtime",
    "PermissionPolicy", "apply_permission_policy",
    "EXECUTION_ENVIRONMENT_COMPONENT", "ExecutionEnvironmentDescription",
    "ActivationScope",
    "ContextPhase",
    "MechanismFamily",
    "MechanismLayer",
    "MechanismContribution",
    "ParameterKind",
    "ParameterDescriptor",
    "MechanismEffects",
    "MechanismDescriptor",
    "MechanismSelection",
    "MechanismInstaller",
    "MechanismDefinition",
    "ResolvedMechanism",
    "LabCatalog",
    "ProviderBinding",
    "ProviderResolver",
    "ArtifactReader",
    "AssemblyContext",
    "AssemblyState",
    "AssemblyResult",
    "assemble_lab",
    "require_workspace_path",
    "builtin_catalog",
]

from .permissions import PermissionPolicy, apply_permission_policy


from .components import ComponentSpec, ResolvedHarness, resolve_harness, verify_runtime, runtime_component_entries
__all__ += ['runtime_component_entries']
from .configuration import (ConfigurationSurface, configure_profile, load_system_config,
                            component_profile, materialize_system, edit_grants, bind_component_changes,
                            configuration_inventory, configuration_resources, restore_component_settings, normalize_configuration_binding)
__all__ += ['ConfigurationSurface', 'configure_profile', 'load_system_config', 'component_profile', 'materialize_system', 'edit_grants', 'bind_component_changes', 'configuration_inventory']
__all__ += ['configuration_resources']
__all__ += ['restore_component_settings']

__all__ += ['normalize_configuration_binding']

from .model_roles import ModelRoleRequirement, RoleProvider, role_alias
__all__ += ['ModelRoleRequirement', 'RoleProvider', 'role_alias']
from .classification import FeatureNode, OptimizationCoverage
from .configuration import validate_component_options, configuration_surfaces, reset_artifact_binding
__all__ += ['FeatureNode', 'OptimizationCoverage', 'validate_component_options', 'configuration_surfaces', 'reset_artifact_binding']


def builtin_catalog() -> LabCatalog:
    """Construct built-ins only when requested, keeping owner imports acyclic."""
    from .builtins import builtin_catalog as build
    return build()

from .optimization import registry_optimization_table, select_default_components, optimization_grants, optimization_table, render_optimization_table
__all__ += ['registry_optimization_table', 'select_default_components', 'optimization_grants', 'optimization_table', 'render_optimization_table']
