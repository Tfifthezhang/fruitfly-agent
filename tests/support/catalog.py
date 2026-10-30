"""Minimal registered mechanisms for Catalog boundary tests."""
from __future__ import annotations
from fruitfly_agent.lab.catalog import MechanismContribution, MechanismDefinition, MechanismDescriptor, MechanismEffects, ParameterDescriptor

def mechanism_definition(
    mechanism_id: str,
    *,
    order: int = 100,
    requires: frozenset[str] = frozenset(),
    conflicts: frozenset[str] = frozenset(),
    group: str | None = None,
    phase: str | None = None,
    install=None,
) -> MechanismDefinition:
    return MechanismDefinition(
        MechanismDescriptor(
            mechanism_id=mechanism_id,
            label=mechanism_id,
            description="test mechanism",
            contributions=(
                MechanismContribution(
                    "online" if phase is not None else "capability",
                    "context" if phase is not None else "tools",
                    phase,
                ),
            ),
            parameters=(
                ParameterDescriptor(
                    "limit",
                    "integer",
                    "Limit",
                    "Positive test limit.",
                    2,
                    minimum=1,
                ),
            ),
            requires=requires,
            conflicts=conflicts,
            exclusive_group=group,
            install_order=order,
            effects=MechanismEffects(tools=(mechanism_id,)),
        ),
        install or (lambda state, context, parameters: state),

        implementation_path='tests/support/catalog.py',
        documentation_path='tests/lab/README.md',
    )
