"""Stable, serializable vocabulary that every selectable mechanism answers."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Literal, Mapping


ParameterKind = Literal[
    "boolean", "integer", "number", "string", "choice", "path", "string_list"
]
MechanismLayer = Literal["capability", "online", "optimization"]
MechanismFamily = Literal["environment", "tools", "context", "workflow"]
ContextPhase = Literal["augmentation", "externalization", "reduction"]
ActivationScope = Literal["live", "next_request", "new_session", "restart"]

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class ParameterDescriptor:
    name: str
    kind: ParameterKind
    label: str
    description: str
    default: Any
    choices: tuple[Any, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    nullable: bool = False
    advanced: bool = False

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.name):
            raise ValueError("parameter name must be a stable identifier")
        if not self.label.strip() or not self.description.strip():
            raise ValueError("parameter label and description must not be empty")
        if self.kind == "choice" and not self.choices:
            raise ValueError("choice parameter requires at least one choice")
        if self.kind != "choice" and self.choices:
            raise ValueError("only choice parameters accept choices")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("parameter minimum cannot exceed maximum")
        self.validate(self.default)

    def validate(self, value: Any) -> Any:
        if value is None:
            if self.nullable:
                return None
            raise ValueError(f"parameter {self.name!r} cannot be null")
        if self.kind == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"parameter {self.name!r} must be a boolean")
            normalized = value
        elif self.kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"parameter {self.name!r} must be an integer")
            normalized = value
        elif self.kind == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"parameter {self.name!r} must be a number")
            normalized = float(value)
        elif self.kind in ("string", "path"):
            if not isinstance(value, str):
                raise ValueError(f"parameter {self.name!r} must be a string")
            if self.kind == "path" and not value.strip():
                raise ValueError(f"parameter {self.name!r} must be a non-empty path")
            normalized = value
        elif self.kind == "choice":
            if value not in self.choices:
                available = ", ".join(repr(item) for item in self.choices)
                raise ValueError(f"parameter {self.name!r} must be one of: {available}")
            normalized = value
        elif self.kind == "string_list":
            if not isinstance(value, (list, tuple)) or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                raise ValueError(
                    f"parameter {self.name!r} must be a list of non-empty strings"
                )
            normalized = tuple(value)
        else:
            raise ValueError(f"unsupported parameter kind: {self.kind!r}")
        if self.kind in ("integer", "number"):
            if self.minimum is not None and normalized < self.minimum:
                raise ValueError(f"parameter {self.name!r} must be at least {self.minimum:g}")
            if self.maximum is not None and normalized > self.maximum:
                raise ValueError(f"parameter {self.name!r} must be at most {self.maximum:g}")
        return normalized

    def parse(self, text: str) -> Any:
        if self.nullable and text.strip().casefold() in {"none", "null"}:
            value: Any = None
        elif self.kind == "boolean":
            lowered = text.strip().casefold()
            if lowered not in {"true", "false", "yes", "no", "on", "off"}:
                raise ValueError("boolean value must be true/false, yes/no, or on/off")
            value = lowered in {"true", "yes", "on"}
        elif self.kind == "integer":
            try:
                value = int(text.strip())
            except ValueError as exc:
                raise ValueError("value must be an integer") from exc
        elif self.kind == "number":
            try:
                value = float(text.strip())
            except ValueError as exc:
                raise ValueError("value must be a number") from exc
        elif self.kind == "string_list":
            value = tuple(item.strip() for item in text.split(",") if item.strip())
        else:
            value = text.strip()
        return self.validate(value)

    def to_dict(self) -> dict[str, Any]:
        default = list(self.default) if isinstance(self.default, tuple) else self.default
        return {
            "name": self.name,
            "kind": self.kind,
            "label": self.label,
            "description": self.description,
            "default": default,
            "choices": list(self.choices),
            "minimum": self.minimum,
            "maximum": self.maximum,
            "nullable": self.nullable,
            "advanced": self.advanced,
        }


@dataclass(frozen=True)
class MechanismContribution:
    layer: MechanismLayer
    family: MechanismFamily
    context_phase: ContextPhase | None = None

    def __post_init__(self) -> None:
        if self.layer not in {"capability", "online", "optimization"}:
            raise ValueError(f"unsupported mechanism layer: {self.layer!r}")
        if self.family not in {"environment", "tools", "context", "workflow"}:
            raise ValueError(f"unsupported mechanism family: {self.family!r}")
        if self.context_phase is not None and self.context_phase not in {
            "augmentation", "externalization", "reduction"
        }:
            raise ValueError(f"unsupported context phase: {self.context_phase!r}")
        is_online_context = self.layer == "online" and self.family == "context"
        if (self.context_phase is not None) != is_online_context:
            raise ValueError(
                "context_phase is required exactly for online/context contributions"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "family": self.family,
            "context_phase": self.context_phase,
        }


@dataclass(frozen=True)
class MechanismEffects:
    uses_provider: bool = False
    uses_network: bool = False
    writes_files: bool = False
    tools: tuple[str, ...] = ()
    lifecycle_hooks: tuple[str, ...] = ()
    cost_notice: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "tools", tuple(self.tools))
        object.__setattr__(self, "lifecycle_hooks", tuple(self.lifecycle_hooks))
        if any(not isinstance(item, str) or not _ID.fullmatch(item) for item in self.tools):
            raise ValueError("mechanism tool effects must be stable identifiers")

    def to_dict(self) -> dict[str, Any]:
        return {
            "uses_provider": self.uses_provider,
            "uses_network": self.uses_network,
            "writes_files": self.writes_files,
            "tools": list(self.tools),
            "lifecycle_hooks": list(self.lifecycle_hooks),
            "cost_notice": self.cost_notice,
        }


@dataclass(frozen=True)
class MechanismDescriptor:
    mechanism_id: str
    label: str
    description: str
    contributions: tuple[MechanismContribution, ...]
    parameters: tuple[ParameterDescriptor, ...] = ()
    capabilities: frozenset[str] = frozenset()
    requires: frozenset[str] = frozenset()
    conflicts: frozenset[str] = frozenset()
    exclusive_group: str | None = None
    default_enabled: bool = False
    install_order: int = 100
    activation: ActivationScope = "new_session"
    effects: MechanismEffects = field(default_factory=MechanismEffects)

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.mechanism_id):
            raise ValueError("mechanism_id must be a stable identifier")
        if not self.label.strip() or not self.description.strip():
            raise ValueError("mechanism label and description must not be empty")
        object.__setattr__(self, "contributions", tuple(self.contributions))
        object.__setattr__(self, "parameters", tuple(self.parameters))
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))
        object.__setattr__(self, "requires", frozenset(self.requires))
        object.__setattr__(self, "conflicts", frozenset(self.conflicts))
        if not self.contributions:
            raise ValueError("mechanism must declare at least one contribution")
        if any(not isinstance(item, MechanismContribution) for item in self.contributions):
            raise TypeError("mechanism contributions must be MechanismContribution values")
        if len(set(self.contributions)) != len(self.contributions):
            raise ValueError("mechanism contributions must be unique")
        if any(not isinstance(item, ParameterDescriptor) for item in self.parameters):
            raise TypeError("mechanism parameters must be ParameterDescriptor values")
        for field_name, values in (
            ("capabilities", self.capabilities),
            ("requires", self.requires),
            ("conflicts", self.conflicts),
        ):
            if any(not isinstance(item, str) or not _ID.fullmatch(item) for item in values):
                raise ValueError(f"mechanism {field_name} must be stable identifiers")
        if self.exclusive_group is not None and not _ID.fullmatch(self.exclusive_group):
            raise ValueError("exclusive_group must be a stable identifier")
        if isinstance(self.install_order, bool) or not isinstance(self.install_order, int):
            raise ValueError("install_order must be an integer")
        if self.activation not in {"live", "next_request", "new_session", "restart"}:
            raise ValueError(f"unsupported activation scope: {self.activation!r}")
        if not isinstance(self.effects, MechanismEffects):
            raise TypeError("mechanism effects must be MechanismEffects")
        names = [item.name for item in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("mechanism parameter names must be unique")

    @property
    def context_phases(self) -> tuple[ContextPhase, ...]:
        return tuple(
            item.context_phase
            for item in self.contributions
            if item.context_phase is not None
        )

    @property
    def primary(self) -> MechanismContribution:
        return self.contributions[0]

    def normalize_parameters(self, values: Mapping[str, Any]) -> dict[str, Any]:
        descriptors = {item.name: item for item in self.parameters}
        unknown = sorted(str(name) for name in values if name not in descriptors)
        if unknown:
            raise ValueError(
                f"unknown parameters for {self.mechanism_id!r}: {', '.join(unknown)}"
            )
        return {
            name: descriptor.validate(values.get(name, descriptor.default))
            for name, descriptor in descriptors.items()
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.mechanism_id,
            "label": self.label,
            "description": self.description,
            "contributions": [item.to_dict() for item in self.contributions],
            "parameters": [item.to_dict() for item in self.parameters],
            "capabilities": sorted(self.capabilities),
            "requires": sorted(self.requires),
            "conflicts": sorted(self.conflicts),
            "exclusive_group": self.exclusive_group,
            "default_enabled": self.default_enabled,
            "install_order": self.install_order,
            "activation": self.activation,
            "effects": self.effects.to_dict(),
        }


__all__ = [
    "ParameterKind", "MechanismLayer", "MechanismFamily", "ContextPhase",
    "ActivationScope", "ParameterDescriptor", "MechanismContribution",
    "MechanismEffects", "MechanismDescriptor",
]
