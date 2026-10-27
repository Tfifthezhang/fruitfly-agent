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
from .builtins import builtin_catalog
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


from .components import ComponentSpec, ResolvedHarness, resolve_harness, verify_runtime
from .configuration import (ConfigurationSurface, configure_profile, load_system_config,
                            component_profile, materialize_system, edit_grants, bind_component_changes,
                            configuration_inventory, configuration_resources, restore_component_settings)
__all__ += ['ConfigurationSurface', 'configure_profile', 'load_system_config', 'component_profile', 'materialize_system', 'edit_grants', 'bind_component_changes', 'configuration_inventory']
__all__ += ['configuration_resources']
__all__ += ['restore_component_settings']
