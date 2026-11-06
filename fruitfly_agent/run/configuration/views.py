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
    for definition in sorted(catalog.definitions(), key=lambda item:
            (tuple(node.order for node in item.feature_path), item.descriptor.install_order, item.descriptor.mechanism_id)):
        descriptor = definition.descriptor
        category = definition.feature_path[0].id
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
                category=category,
                label=descriptor.label,
                description=descriptor.description,
                enabled=enabled,
                activation=descriptor.activation,
                layer=descriptor.primary.layer,
                family=descriptor.primary.family,
                context_phase=descriptor.primary.context_phase,
                display_section=display_section(definition),
                feature_path=tuple((node.id, node.label, node.order) for node in definition.feature_path),
                visible=definition.visible and definition.configurable,
                parameters=parameters,
                effects=_effect_messages(descriptor.effects),
                requires=tuple(sorted(descriptor.requires)),
                conflicts=tuple(sorted(descriptor.conflicts)),
                exclusive_group=descriptor.exclusive_group,
                selection_group=catalog.get(descriptor.mechanism_id).selection_group,
                selection_group_label=catalog.get(descriptor.mechanism_id).selection_group_label,
                selection_group_allow_disabled=catalog.get(descriptor.mechanism_id).selection_group_allow_disabled,
                implementation_path=definition.implementation_path,
                documentation_path=definition.documentation_path,
                input_parameters=definition.input_parameters,
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


def display_section(definition) -> str | None:
    return definition.feature_path[1].id if len(definition.feature_path) > 1 else None


def display_group(definition) -> str:
    return definition.feature_path[0].id
