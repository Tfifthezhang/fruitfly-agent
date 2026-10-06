"""Explicit, immutable catalog for built-in and injected Lab mechanisms."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .assembly import AssemblyContext, AssemblyState

CatalogBootstrap = Callable[["AssemblyState", "AssemblyContext"], "AssemblyState"]

from .models import (
    MechanismDefinition,
    MechanismDescriptor,
    MechanismSelection,
    ResolvedMechanism,
)


class LabCatalog:
    """Resolve selections without scanning packages or mutating global state."""

    def __init__(self, definitions: Iterable[MechanismDefinition], *, bootstrap: CatalogBootstrap | None = None) -> None:
        if bootstrap is not None and not callable(bootstrap):
            raise TypeError("catalog bootstrap must be callable")
        self.bootstrap = bootstrap
        items = tuple(definitions)
        by_id: dict[str, MechanismDefinition] = {}
        for definition in items:
            mechanism_id = definition.descriptor.mechanism_id
            if mechanism_id in by_id:
                raise ValueError(f"duplicate mechanism id: {mechanism_id!r}")
            by_id[mechanism_id] = definition
        groups: dict[str, list[MechanismDefinition]] = {}
        for definition in items:
            if definition.selection_group is not None:
                groups.setdefault(definition.selection_group, []).append(definition)
        for group_id, members in groups.items():
            metadata = {(item.selection_group_label, item.selection_group_allow_disabled) for item in members}
            if len(metadata) != 1:
                raise ValueError(f"selection group {group_id!r} has inconsistent display or disable policy")
            if len(members) > 1:
                exclusive = {item.descriptor.exclusive_group for item in members}
                if len(exclusive) != 1 or None in exclusive:
                    raise ValueError(f"multi-option selection group {group_id!r} must share an exclusive group")
                locations = {(item.descriptor.primary.family, item.descriptor.primary.layer,
                              item.descriptor.primary.context_phase) for item in members}
                if len(locations) != 1:
                    raise ValueError(f"selection group {group_id!r} must have one display location")
        self._definitions = by_id

    def definitions(self) -> tuple[MechanismDefinition, ...]:
        return tuple(
            self._definitions[key]
            for key in sorted(self._definitions)
        )

    def descriptors(self) -> tuple[MechanismDescriptor, ...]:
        return tuple(item.descriptor for item in self.definitions())

    def get(self, mechanism_id: str) -> MechanismDefinition:
        try:
            return self._definitions[mechanism_id]
        except KeyError as exc:
            available = ", ".join(sorted(self._definitions)) or "none"
            raise ValueError(
                f"unknown mechanism {mechanism_id!r} (available: {available}). "
                "Remove this selection or register the mechanism in the Catalog."
            ) from exc

    def extended(
        self,
        definitions: Iterable[MechanismDefinition],
    ) -> "LabCatalog":
        """Return a new catalog with explicitly injected app mechanisms."""

        return LabCatalog((*self.definitions(), *tuple(definitions)), bootstrap=self.bootstrap)

    def default_selections(self) -> tuple[MechanismSelection, ...]:
        return tuple(
            MechanismSelection(
                definition.descriptor.mechanism_id,
                parameters={
                    item.name: item.default
                    for item in definition.descriptor.parameters
                },
            )
            for definition in sorted(
                self._definitions.values(),
                key=lambda item: (
                    item.descriptor.install_order,
                    item.descriptor.mechanism_id,
                ),
            )
            if definition.descriptor.default_enabled
        )

    def resolve(
        self,
        selections: Sequence[MechanismSelection],
    ) -> tuple[ResolvedMechanism, ...]:
        seen: set[str] = set()
        resolved: list[ResolvedMechanism] = []
        for selection in selections:
            if selection.mechanism_id in seen:
                raise ValueError(
                    f"duplicate mechanism selection: {selection.mechanism_id!r}"
                )
            seen.add(selection.mechanism_id)
            definition = self.get(selection.mechanism_id)
            if definition.validate_parameters is not None:
                definition.validate_parameters(selection.parameters)
            parameters = definition.descriptor.normalize_parameters(
                selection.parameters
            )
            if selection.enabled:
                resolved.append(ResolvedMechanism(definition, parameters))

        enabled = {
            item.definition.descriptor.mechanism_id for item in resolved
        }
        for item in resolved:
            descriptor = item.definition.descriptor
            missing = sorted(descriptor.requires - enabled)
            if missing:
                raise ValueError(
                    f"mechanism {descriptor.mechanism_id!r} requires: "
                    f"{', '.join(missing)}"
                )
            conflicts = sorted(descriptor.conflicts & enabled)
            if conflicts:
                raise ValueError(
                    f"mechanism {descriptor.mechanism_id!r} conflicts with: "
                    f"{', '.join(conflicts)}"
                )

        groups: dict[str, list[str]] = {}
        for item in resolved:
            descriptor = item.definition.descriptor
            if descriptor.exclusive_group is None:
                continue
            groups.setdefault(descriptor.exclusive_group, []).append(
                descriptor.mechanism_id
            )
        collisions = {
            group: ids for group, ids in groups.items() if len(ids) > 1
        }
        if collisions:
            detail = "; ".join(
                f"{group}: {', '.join(sorted(ids))}"
                for group, ids in sorted(collisions.items())
            )
            raise ValueError(f"exclusive mechanism groups violated: {detail}")

        context_slots: dict[str, list[str]] = {}
        for item in resolved:
            descriptor = item.definition.descriptor
            for phase in descriptor.context_phases:
                if phase == "reduction":
                    context_slots.setdefault(phase, []).append(
                        descriptor.mechanism_id
                    )
        context_collisions = {
            phase: ids for phase, ids in context_slots.items() if len(ids) > 1
        }
        if context_collisions:
            detail = "; ".join(
                f"{phase}: {', '.join(sorted(ids))}"
                for phase, ids in sorted(context_collisions.items())
            )
            raise ValueError(f"exclusive context phases violated: {detail}")

        # Dependencies determine order; numeric order only breaks independent ties.
        dependencies = {}
        for item in resolved:
            definition = item.definition
            required = set(definition.descriptor.requires)
            for capability in definition.requires_capabilities:
                providers = [other.definition.descriptor.mechanism_id for other in resolved
                             if capability in other.definition.provides]
                if len(providers) != 1:
                    raise ValueError(f"mechanism {definition.descriptor.mechanism_id!r} requires exactly one provider of capability {capability!r}")
                required.add(providers[0])
            dependencies[definition.descriptor.mechanism_id] = required
        ordered = []
        remaining = {item.definition.descriptor.mechanism_id: item for item in resolved}
        while remaining:
            ready = [item for key, item in remaining.items() if not dependencies[key] & remaining.keys()]
            if not ready:
                raise ValueError("cyclic mechanism dependencies")
            ready.sort(key=lambda item: (item.definition.descriptor.install_order, item.definition.descriptor.mechanism_id))
            item = ready[0]
            ordered.append(item)
            del remaining[item.definition.descriptor.mechanism_id]
        return tuple(ordered)

    def capability_dependencies(self, mechanism_id, selections):
        """Resolve UI dependency choices without naming an implementation in Run."""
        definition = self.get(mechanism_id)
        result = set(definition.descriptor.requires)
        enabled = {s.mechanism_id for s in selections if s.enabled}
        for capability in definition.requires_capabilities:
            providers = [d for d in self.definitions() if capability in d.provides]
            active = [d for d in providers if d.descriptor.mechanism_id in enabled]
            defaults = [d for d in providers if d.descriptor.default_enabled]
            choices = active or defaults or providers
            if len(choices) != 1:
                raise ValueError(f"select one provider of capability {capability!r} first")
            result.add(choices[0].descriptor.mechanism_id)
        return frozenset(result)


__all__ = ["LabCatalog"]
