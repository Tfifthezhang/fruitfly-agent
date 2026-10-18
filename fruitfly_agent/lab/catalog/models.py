"""Lab selection and installer values built on Core mechanism descriptors."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
import re
from typing import Any, Callable, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from .assembly import AssemblyContext, AssemblyState

from fruitfly_agent.lab.improvement.methods import MethodDefinition

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


@dataclass(frozen=True)
class MechanismSelection:
    mechanism_id: str
    enabled: bool = True
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.mechanism_id):
            raise ValueError("selection mechanism_id must be a stable identifier")
        if not isinstance(self.enabled, bool):
            raise ValueError("selection enabled must be a boolean")
        if not isinstance(self.parameters, Mapping):
            raise ValueError("selection parameters must be a mapping")
        object.__setattr__(self, "parameters", dict(self.parameters))

    def to_dict(self) -> dict[str, Any]:
        values = {
            name: list(value) if isinstance(value, tuple) else value
            for name, value in self.parameters.items()
        }
        return {"id": self.mechanism_id, "enabled": self.enabled, "parameters": values}


MechanismInstaller = Callable[["AssemblyState", "AssemblyContext", Mapping[str, Any]], "AssemblyState"]


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
    improvement: MethodDefinition | None = None
    implementation_path: str = ''
    documentation_path: str = ''
    input_parameters: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.improvement is not None:
            if not isinstance(self.improvement, MethodDefinition):
                raise TypeError('improvement must be a MethodDefinition')
            if not any(c.layer == 'improvement' for c in self.descriptor.contributions):
                raise ValueError('an improvement method must declare its improvement contribution')
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
]
