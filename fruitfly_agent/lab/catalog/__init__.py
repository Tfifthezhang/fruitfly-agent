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
from fruitfly_agent.lab.learning.engine import build_learning
from fruitfly_agent.lab.learning.registration import LEARNING_POLICY_COMPONENT, LEARNING_PROCESSOR_COMPONENT
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

from fruitfly_agent.lab.improvement.migration import migrate_legacy_improvement_config_text, migrate_legacy_improvement_candidate

__all__ = [
    "build_learning", "LEARNING_POLICY_COMPONENT", "LEARNING_PROCESSOR_COMPONENT",
    "migrate_legacy_improvement_config_text", "migrate_legacy_improvement_candidate",
    "PermissionPolicy", "apply_permission_policy",
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

