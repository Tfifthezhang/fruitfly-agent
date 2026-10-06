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
