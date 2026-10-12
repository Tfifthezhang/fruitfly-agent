"""Project resolved configuration into frontend-owned menu values."""

from __future__ import annotations

from fruitfly_agent.interactive import ConfigurationMechanism, ConfigurationParameter, ConfigurationSelectionGroup
from fruitfly_agent.lab.catalog import LabCatalog
from fruitfly_agent.lab.base_prompt import builtins

from .profile import HarnessProfile


def mechanism_views(profile: HarnessProfile, catalog: LabCatalog, warnings: list[str]):
    selections = {
        item.mechanism_id: item for item in profile.mechanisms
    }
    mechanisms: list[ConfigurationMechanism] = []
    for descriptor in sorted(
        catalog.descriptors(),
        key=lambda item: (
            display_group(item),
            _context_phase_order(item),
            item.install_order,
            item.mechanism_id,
        ),
    ):
        selection = selections.get(descriptor.mechanism_id)
        enabled = selection.enabled if selection is not None else False
        raw_parameters = selection.parameters if selection is not None else {}
        try:
            values = descriptor.normalize_parameters(raw_parameters)
        except ValueError as exc:
            warnings.append(str(exc))
            values = {
                item.name: raw_parameters.get(item.name, item.default)
                for item in descriptor.parameters
            }
        parameters = tuple(
            ConfigurationParameter(
                name=item.name,
                label=item.label,
                description=item.description,
                kind=item.kind,
                value=values[item.name],
                choices=item.choices,
                advanced=item.advanced,
                minimum=item.minimum,
                maximum=item.maximum,
                nullable=item.nullable,
            )
            for item in descriptor.parameters
        )
        mechanisms.append(
            ConfigurationMechanism(
                mechanism_id=descriptor.mechanism_id,
                category=display_group(descriptor),
                label=descriptor.label,
                description=descriptor.description,
                enabled=enabled,
                activation=descriptor.activation,
                layer=descriptor.primary.layer,
                family=descriptor.primary.family,
                context_phase=descriptor.primary.context_phase,
                display_section=display_section(descriptor),
                visible=catalog.get(descriptor.mechanism_id).visible,
                parameters=parameters,
                effects=_effect_messages(descriptor.effects),
                requires=tuple(sorted(descriptor.requires)),
                conflicts=tuple(sorted(descriptor.conflicts)),
                exclusive_group=descriptor.exclusive_group,
                selection_group=catalog.get(descriptor.mechanism_id).selection_group,
                selection_group_label=catalog.get(descriptor.mechanism_id).selection_group_label,
                selection_group_allow_disabled=catalog.get(descriptor.mechanism_id).selection_group_allow_disabled,
            )
        )
    selection_groups = []
    grouped_definitions: dict[str, list] = {}
    for mechanism in mechanisms:
        if mechanism.selection_group is not None:
            grouped_definitions.setdefault(mechanism.selection_group, []).append(mechanism)
    for group_id, options in sorted(grouped_definitions.items()):
        enabled_options = [item.mechanism_id for item in options if item.enabled]
        selection_groups.append(ConfigurationSelectionGroup(
            group_id=group_id,
            label=options[0].selection_group_label or group_id,
            category=options[0].category,
            section=options[0].display_section,
            option_ids=tuple(item.mechanism_id for item in options),
            selected_id=enabled_options[0] if enabled_options else None,
            allow_disabled=options[0].selection_group_allow_disabled,
        ))
    return tuple(mechanisms), tuple(selection_groups)


def prompt_choices(profile: HarnessProfile):
    options = {prompt.prompt_id: prompt.label for prompt in builtins()}
    builtin_ids = tuple(options)
    if profile.prompt not in options:
        options[profile.prompt] = 'Current selected prompt'
    adapted_ids = tuple(ref for ref in options if ref not in builtin_ids)
    groups = (("builtin", "Built-in prompts", builtin_ids, False),
              ("adapted", "Task / scenario adapted prompts", adapted_ids, True))
    return tuple(options), tuple(options.items()), groups


def _effect_messages(effects) -> tuple[str, ...]:
    rows = []
    if effects.uses_provider:
        rows.append("uses an auxiliary Provider")
    if effects.uses_network:
        rows.append("may access the network and incur cost")
    if effects.writes_files:
        rows.append("writes persistent files or session metadata")
    if effects.tools:
        rows.append("adds tools: " + ", ".join(effects.tools))
    if effects.lifecycle_hooks:
        rows.append("hooks: " + ", ".join(effects.lifecycle_hooks))
    if effects.cost_notice:
        rows.append(effects.cost_notice)
    return tuple(rows)


def display_section(descriptor) -> str | None:
    contribution = descriptor.primary
    if contribution.family != "context":
        return None
    if contribution.context_phase is not None:
        return contribution.context_phase
    if contribution.layer == "capability":
        return "augmentation"
    return None


def _context_phase_order(descriptor) -> int:
    phase = display_section(descriptor)
    return {
        "augmentation": 0,
        "externalization": 1,
        "reduction": 2,
        None: 4,
    }[phase]


def display_group(descriptor) -> str:
    """Project Core mechanism coordinates into the current application menu."""
    contribution = descriptor.primary
    if contribution.layer == "optimization":
        return "optimization"
    if contribution.family == "context":
        return "context-manager"
    return contribution.family

