"""Lab selection and installer values built on Core mechanism descriptors."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
import re
from typing import Any, Callable, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from .assembly import AssemblyContext, AssemblyState


from fruitfly_agent.core.mechanisms import (
    ActivationScope,
    ContextPhase,
    MechanismContribution,
    MechanismDescriptor,
    MechanismEffects,
    MechanismFamily,
    MechanismLayer,
    ParameterDescriptor,
    ParameterKind,
)

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


from fruitfly_agent.runtime_spec.selections import MechanismSelection


MechanismInstaller = Callable[["AssemblyState", "AssemblyContext", Mapping[str, Any]], "AssemblyState"]


@dataclass(frozen=True)
class SetupCredential:
    parameter: str
    label: str
    description: str
    variable: str = ''
    allow_whitespace: bool = True


@dataclass(frozen=True)
class MechanismSetup:
    fields: tuple[str, ...]
    credentials: tuple[SetupCredential, ...] = ()
    required_fields: tuple[str, ...] = ()
    guidance: str = ''
    credential_resolver: Callable[[Mapping[str, Any]], tuple[SetupCredential, ...]] | None = None


@dataclass(frozen=True)
class MechanismDefinition:
    descriptor: MechanismDescriptor
    install: MechanismInstaller
    implementation_id: str | None = None
    visible: bool = True
    artifact_slots: frozenset[str] = frozenset()
    provides: frozenset[str] = frozenset()
    requires_capabilities: frozenset[str] = frozenset()
    validate_parameters: Callable[[Mapping[str, Any]], None] | None = None
    selection_group: str | None = None
    selection_group_label: str | None = None
    selection_group_allow_disabled: bool = True
    configuration_category: str | None = None
    implementation_path: str = ''
    documentation_path: str = ''
    input_parameters: tuple[str, ...] = ()
    setup: MechanismSetup | None = None
    credential_variables: Callable[[Mapping[str, Any]], tuple[str, ...]] | None = None
    model_profiles: Callable[[Mapping[str, Any]], tuple[str, ...]] | None = None
    prepare_targets: Callable[[Any, Any], Any] | None = None
    component_specs: Callable[[Mapping[str, Any], bool], tuple] | None = None
    execution_fields: frozenset[str] = frozenset()
    component_validator: Callable | None = None
    tool_provider: Callable | None = None
    configuration_role: str = 'H'
    configuration_surfaces: tuple = ()
    model_role_parameters: Mapping[str, str] = field(default_factory=dict)
    configuration_edit: Callable | None = None
    configuration_snapshot: Callable | None = None

    def __post_init__(self) -> None:
        if self.configuration_role not in {'H', 'S', 'I'}:
            raise ValueError('configuration role must be H/S/I')
        if self.configuration_edit is not None and not callable(self.configuration_edit):
            raise TypeError('configuration edit normalizer must be callable')
        if self.configuration_snapshot is not None and not callable(self.configuration_snapshot):
            raise TypeError('configuration snapshot must be callable')
        if (not isinstance(self.model_role_parameters, Mapping)
                or set(self.model_role_parameters.values()) - {p.name for p in self.descriptor.parameters}):
            raise ValueError('model roles must bind declared parameter fields')
        for callback in (self.component_specs, self.component_validator, self.tool_provider):
            if callback is not None and not callable(callback):
                raise TypeError('component metadata callbacks must be callable')
        from fruitfly_agent.runtime_spec.execution import flatten_execution
        if isinstance(self.execution_fields, str) or set(self.execution_fields) - set(flatten_execution({})):
            raise ValueError('execution_fields must name declared scalar execution fields')
        object.__setattr__(self, 'execution_fields', frozenset(self.execution_fields))
        if self.prepare_targets is not None and not callable(self.prepare_targets):
            raise TypeError('object target preparation must be callable')
        if self.configuration_category is not None and not _ID.fullmatch(self.configuration_category):
            raise ValueError('configuration category must be a stable identifier')
        if self.implementation_id is not None and (
            not isinstance(self.implementation_id, str) or not _ID.fullmatch(self.implementation_id)
        ):
            raise ValueError("implementation_id must be a stable version identifier")
        if not isinstance(self.visible, bool):
            raise TypeError("mechanism visible must be boolean")
        for name in ("artifact_slots", "provides", "requires_capabilities"):
            values = getattr(self, name)
            if isinstance(values, str):
                raise ValueError(f"{name} must contain stable identifiers")
            values = tuple(values)
            if any(not isinstance(value, str) or not _ID.fullmatch(value) for value in values):
                raise ValueError(f"{name} must contain stable identifiers")
            object.__setattr__(self, name, frozenset(values))
        if self.validate_parameters is not None and not callable(self.validate_parameters):
            raise TypeError("parameter validator must be callable")
        if self.credential_variables is not None and not callable(self.credential_variables):
            raise TypeError("credential_variables must be callable")
        if self.model_profiles is not None and not callable(self.model_profiles):
            raise TypeError("model_profiles must be callable")
        if not callable(self.install):
            raise TypeError("mechanism installer must be callable")
        if self.selection_group is not None and not _ID.fullmatch(self.selection_group):
            raise ValueError("selection_group must be a stable identifier")
        if self.selection_group_label is not None and (
            not isinstance(self.selection_group_label, str) or not self.selection_group_label.strip()
        ):
            raise ValueError("selection_group_label must be non-empty text")
        if (self.selection_group is None) != (self.selection_group_label is None):
            raise ValueError("selection group ID and label must be provided together")
        if not isinstance(self.selection_group_allow_disabled, bool):
            raise TypeError("selection_group_allow_disabled must be boolean")
        if self.selection_group is None and self.selection_group_allow_disabled is not True:
            raise ValueError("a mechanism without a selection group cannot set its disabled policy")
        if not self.descriptor.description.strip() or any(c in self.descriptor.description for c in '\r\n\x1b'):
            raise ValueError('algorithm description must be a nonempty single line')
        for name, suffix in (('implementation_path', '.py'), ('documentation_path', '.md')):
            value = getattr(self, name)
            if (not isinstance(value, str) or not value.strip() or not value.endswith(suffix)
                    or any(ord(c) < 32 for c in value) or '..' in PurePosixPath(value).parts):
                raise ValueError(f'algorithm {name} must name an explicit {suffix} file')
        if isinstance(self.input_parameters, str):
            raise ValueError('input_parameters must contain declared parameter names')
        names = tuple(self.input_parameters)
        if len(set(names)) != len(names) or set(names) - {p.name for p in self.descriptor.parameters}:
            raise ValueError('input_parameters must contain distinct declared parameter names')
        object.__setattr__(self, 'input_parameters', names)
        if self.setup is not None:
            parameters = {p.name: p for p in self.descriptor.parameters}
            fields = (*self.setup.fields, *(c.parameter for c in self.setup.credentials))
            if (len(self.setup.fields) != len(set(self.setup.fields))
                    or len(self.setup.credentials) != len({c.parameter for c in self.setup.credentials})
                    or set(fields) - parameters.keys()):
                raise ValueError('setup fields must name distinct declared parameters')
            if set(self.setup.required_fields) - set(self.setup.fields):
                raise ValueError('required setup fields must be visible form fields')
            if any(parameters[c.parameter].kind != 'string' for c in self.setup.credentials):
                raise ValueError('credential bindings must name string parameters')
            if self.setup.credential_resolver is not None and not callable(self.setup.credential_resolver):
                raise TypeError('setup credential_resolver must be callable')

    def setup_credentials(self, parameters: Mapping[str, Any]) -> tuple[SetupCredential, ...]:
        """Resolve hidden form fields from the current form's non-secret values."""
        if self.setup is None:
            return ()
        fields = (self.setup.credential_resolver(parameters) if self.setup.credential_resolver is not None
                  else self.setup.credentials)
        declared = {p.name: p for p in self.descriptor.parameters}
        if (not isinstance(fields, tuple) or any(not isinstance(c, SetupCredential)
                or c.parameter not in declared or declared[c.parameter].kind != 'string'
                or not isinstance(c.variable, str)
                or c.variable and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', c.variable)
                or not isinstance(c.allow_whitespace, bool) for c in fields)
                or len(fields) != len({c.parameter for c in fields})):
            raise ValueError('setup credentials must bind distinct string parameters and valid secret variable names')
        return fields

    def required_credentials(self, parameters: Mapping[str, Any]) -> tuple[str, ...]:
        """Return declared secret names offline; never read or return their values."""
        if self.credential_variables is None:
            return ()
        if self.validate_parameters is not None:
            self.validate_parameters(parameters)
        normalized = self.descriptor.normalize_parameters(parameters)
        names = self.credential_variables(normalized)
        if (not isinstance(names, tuple) or any(not isinstance(name, str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in names)):
            raise ValueError("credential_variables must return a tuple of environment variable names")
        return tuple(sorted(set(names)))


@dataclass(frozen=True)
class ResolvedMechanism:
    definition: MechanismDefinition
    parameters: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", dict(self.parameters))


__all__ = [
    "ParameterKind", "MechanismLayer", "MechanismFamily", "ContextPhase",
    "ActivationScope", "ParameterDescriptor", "MechanismContribution",
    "MechanismEffects", "MechanismDescriptor", "MechanismSelection",
    "MechanismInstaller", "MechanismDefinition", "ResolvedMechanism",
    "MechanismSetup", "SetupCredential",
]
