"""Pure configuration-menu projection; no controllers, I/O or persistence."""

from dataclasses import dataclass

from fruitfly_agent.interactive.contracts.configuration import (
    ConfigurationMechanism, ConfigurationParameter, ConfigurationSnapshot,
)
from fruitfly_agent.interactive.terminal.io.menu import MenuHelp, MenuRow


@dataclass(frozen=True)
class ConfigurationMenuAction:
    kind: str
    key: str = ''
    options: tuple[str, ...] = ()
    active: str | None = None
    allow_disabled: bool = True
    declared: bool = False
    parameter: ConfigurationParameter | None = None

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.kind, self.key, self.parameter.name if self.parameter is not None
                else self.active or '' if self.kind in {'choose', 'settings', 'setup'} else '')


def has_settings(item: ConfigurationMechanism) -> bool:
    return item.setup_available or any(p.name in item.input_parameters for p in item.parameters)


def category_rows(
    snapshot: ConfigurationSnapshot, category: str, expanded: str | None,
    *, original: ConfigurationSnapshot | None = None,
) -> tuple[list[MenuRow], list[ConfigurationMenuAction]]:
    """Use declared groups and fields without recognizing concrete algorithms."""
    mechanisms = tuple(item for item in snapshot.mechanisms if item.category == category and item.visible)
    by_id = {item.mechanism_id: item for item in mechanisms}
    groups = [group for group in snapshot.selection_groups if group.category == category
              and group.option_ids and all(option in by_id for option in group.option_ids)]
    grouped_ids = {option for group in groups for option in group.option_ids}
    entries = [(group.group_id, group.label, group.option_ids, group.selected_id,
                group.allow_disabled, True, group.section) for group in groups]
    entries += [(item.mechanism_id, item.label, (item.mechanism_id,),
                 item.mechanism_id if item.enabled else None, True, False,
                 item.display_section or item.context_phase)
                for item in mechanisms if item.mechanism_id not in grouped_ids]
    order = {'augmentation': 0, 'externalization': 1, 'reduction': 2}
    entries.sort(key=lambda entry: order.get(entry[6] or '', 3))
    before = {item.mechanism_id: item for item in original.mechanisms} if original else {}
    rows: list[MenuRow] = []
    actions: list[ConfigurationMenuAction] = []
    for key, label, options, active, allow_disabled, declared, section in entries:
        multiple = len(options) > 1
        current = by_id[active] if active else by_id[options[0]]
        heading = 'Context ' + section if section in order else (section or '')
        summary = ' · ' + current.label if active and multiple else ''
        suffix = (' ▴' if expanded == key else ' ▾') if multiple else (' ›' if has_settings(current) else '')
        explanation = current.description if active or not multiple else 'Choose an implementation.'
        rows.append(MenuRow(label + summary + suffix, marker='[✓]' if active else '[ ]',
            section=heading, state='enabled' if active else '',
            changed=bool(before) and any(before.get(option) != by_id[option] for option in options),
            help=MenuHelp(current.label if active else label, explanation)))
        actions.append(ConfigurationMenuAction('expand', key, options, active, allow_disabled, declared))
        if multiple and expanded == key:
            for option in options:
                item = by_id[option]
                rows.append(MenuRow(item.label, marker='●' if option == active else '○', depth=1,
                    section=heading, state='selected' if option == active else '',
                    help=MenuHelp(item.label, item.description)))
                actions.append(ConfigurationMenuAction('choose', key, options, option, allow_disabled, declared))
            if active and has_settings(current):
                rows.append(MenuRow('Settings…', depth=1, section=heading,
                    help=MenuHelp(current.label, current.description)))
                actions.append(ConfigurationMenuAction('settings', key, active=active))
    rows.append(MenuRow('Back', help=MenuHelp('Back', 'Return to configuration.')))
    actions.append(ConfigurationMenuAction('back'))
    return rows, actions


def settings_rows(
    item: ConfigurationMechanism, *, original: ConfigurationSnapshot,
) -> tuple[list[MenuRow], list[ConfigurationMenuAction]]:
    rows: list[MenuRow] = []
    actions: list[ConfigurationMenuAction] = []
    if item.setup_available:
        rows.append(MenuRow('Set up…', help=MenuHelp('Set up ' + item.label, item.setup_status or item.description)))
        actions.append(ConfigurationMenuAction('setup', item.mechanism_id, active=item.mechanism_id))
    prior = next((m for m in original.mechanisms if m.mechanism_id == item.mechanism_id), None)
    for parameter in item.parameters:
        if parameter.name not in item.input_parameters:
            continue
        old = next((p for p in prior.parameters if p.name == parameter.name), None) if prior else None
        rows.append(MenuRow(f'{parameter.label} · {parameter.value}',
            changed=bool(old and old.value != parameter.value),
            help=MenuHelp(parameter.label, parameter.description)))
        actions.append(ConfigurationMenuAction('parameter', item.mechanism_id,
            active=item.mechanism_id, parameter=parameter))
    rows.append(MenuRow('Back', help=MenuHelp('Back', 'Return to component choices.')))
    actions.append(ConfigurationMenuAction('back'))
    return rows, actions
