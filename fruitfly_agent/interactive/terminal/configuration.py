"""Provider-free, option-driven startup configuration center."""

from __future__ import annotations

import sys
from typing import Any, TextIO

from ..configuration import (
    ConfigurationController,
    ConfigurationLaunchResult,
    ConfigurationMechanism,
    ConfigurationSnapshot,
)
from .input import LineEditor, create_line_editor
from .menu import (
    MenuAction,
    MenuEvent,
    MenuInput,
    MenuRow,
    TerminalMenuRenderer,
    create_menu_input,
)


class TerminalConfigurationFrontend:
    """Render generic session choices without knowing concrete Lab components."""

    def __init__(
        self,
        configuration: ConfigurationController,
        *,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
        line_editor: LineEditor | None = None,
        menu_input: MenuInput | None = None,
        active_prompt_label: str | None = None,
    ) -> None:
        self.configuration = configuration
        self.input = input_stream or sys.stdin
        self.output = output_stream or sys.stdout
        self.line_editor = line_editor or create_line_editor(self.input, self.output)
        self.menu_input = menu_input or create_menu_input(
            self.input,
            self.output,
            self.line_editor,
        )
        self.renderer = TerminalMenuRenderer(self.output)
        self.notice = ""
        self._inside_active_session = False
        self.active_prompt_label = active_prompt_label

    def run(self, *, editable: bool = True) -> ConfigurationLaunchResult:
        return self._new_session_loop() if editable else self._resume_loop()

    def run_for_active_session(self) -> ConfigurationLaunchResult:
        """Edit future-session choices without ever exiting the Agent client."""
        self._inside_active_session = True
        try:
            while True:
                self._configure_loop(back_detail="Review changes before returning")
                snapshot = self.configuration.snapshot()
                if not snapshot.changed:
                    return ConfigurationLaunchResult(start=False)
                decision = self._confirm_new_session_loop(snapshot)
                if decision == "continue":
                    continue
                if decision == "discard":
                    try:
                        self.configuration.reset()
                    except (OSError, TypeError, ValueError) as exc:
                        self.notice = f"Could not discard configuration: {exc}"
                        continue
                    return ConfigurationLaunchResult(start=False)
                result = self._start(snapshot)
                if result is not None:
                    return result
        finally:
            self._inside_active_session = False

    def _new_session_loop(self) -> ConfigurationLaunchResult:
        selected = 0
        while True:
            snapshot = self.configuration.snapshot()
            enabled = sum(item.enabled for item in snapshot.mechanisms if item.visible)
            rows = (
                MenuRow("Start new session", _session_summary(snapshot, enabled)),
                MenuRow("Configure", "Choose the model and runtime components"),
                MenuRow("Exit", "Leave without creating a session"),
            )
            self._render(title="FruitFlyAgent",
                         subtitle="Ready to start. Open configuration only when needed.",
                         rows=rows, selected=selected)
            event = self.menu_input.read_event()
            selected, handled = _navigate(event, selected, len(rows))
            if handled:
                continue
            if event.action == MenuAction.QUIT:
                return ConfigurationLaunchResult(start=False)
            if event.action != MenuAction.ACTIVATE:
                continue
            if selected == 0:
                result = self._start(snapshot)
                if result is not None:
                    return result
            elif selected == 1:
                if self._configure_loop():
                    return ConfigurationLaunchResult(start=False)
            else:
                return ConfigurationLaunchResult(start=False)

    def _preview_prompt(self, label, content_hash, content):
        """Preview complete prompt text before staging a future-session choice."""
        import textwrap
        lines = [part for line in content.splitlines()
                 for part in (textwrap.wrap(line, width=80, replace_whitespace=False) or [''])]
        page, selected, size = 0, 1, 8
        values = ('Use for next session', 'Back')
        while True:
            self._render(title='Base prompt preview',
                subtitle=f'{label} · {content_hash}\nReview prompt ({page + 1}/{max(1, (len(lines) + size - 1)//size)})\n'
                         + '\n'.join(lines[page*size:(page+1)*size])
                         + '\nPageUp/PageDown: text pages',
                rows=tuple(MenuRow(value) for value in values), selected=selected)
            event = self.menu_input.read_event()
            selected, handled = _navigate(event, selected, len(values))
            if handled:
                continue
            if event.action == MenuAction.PAGE_UP:
                page = max(0, page - 1)
            elif event.action == MenuAction.PAGE_DOWN:
                page = min(max(0, (len(lines)-1)//size), page + 1)
            elif event.action == MenuAction.QUIT:
                return True, _CANCELLED
            elif event.action == MenuAction.BACK:
                return False, _CANCELLED
            elif event.action == MenuAction.ACTIVATE:
                return False, values[selected]

    def _configure_loop(
        self,
        *,
        back_detail: str = "Return to startup",
    ) -> bool:
        selected = 0
        while True:
            snapshot = self.configuration.snapshot()
            categories = _group_mechanisms(snapshot)
            rows = [
                MenuRow("Model", snapshot.model_profile or "Select a model"),
                MenuRow("Base prompt", f"{snapshot.prompt_label} · next session"),
            ]
            rows.extend(
                MenuRow(
                    _category_label(category),
                    _category_summary(mechanisms),
                )
                for category, mechanisms in categories
            )
            rows.append(MenuRow("Back", back_detail))
            self._render(
                title="Configuration",
                subtitle=(
                    "Choose the model, runtime components, and primary "
                    "algorithm selections."
                ),
                rows=tuple(rows),
                selected=selected,
            )
            event = self.menu_input.read_event()
            selected, handled = _navigate(event, selected, len(rows))
            if handled:
                continue
            if event.action == MenuAction.QUIT:
                return True
            if event.action == MenuAction.BACK or selected == len(rows) - 1:
                return False
            if event.action != MenuAction.ACTIVATE:
                continue
            if selected == 0:
                if self._choose_model(snapshot):
                    return True
            elif selected == 1:
                if self._choose_prompt(snapshot):
                    return True
            elif selected <= len(categories) + 1:
                category = categories[selected - 2][0]
                if self._category_loop(category):
                    return True

    def _confirm_new_session_loop(
        self,
        snapshot: ConfigurationSnapshot,
    ) -> str:
        selected = 0
        rows = (
            MenuRow(
                "Save and start new session",
                f"base prompt: {self.active_prompt_label or 'current'} → {snapshot.prompt_label} (next)",
            ),
            MenuRow("Continue configuring", "Return to the configuration menu"),
            MenuRow(
                "Discard changes",
                "Keep using the current session and its existing configuration",
            ),
        )
        while True:
            self._render(
                title="New session required",
                subtitle=(
                    "Configuration cannot replace the Provider or components in "
                    "the active session. Start a fresh session to apply it."
                ),
                rows=rows,
                selected=selected,
            )
            event = self.menu_input.read_event()
            selected, handled = _navigate(event, selected, len(rows))
            if handled:
                continue
            if event.action == MenuAction.BACK:
                return "continue"
            if event.action == MenuAction.QUIT:
                return "discard"
            if event.action != MenuAction.ACTIVATE:
                continue
            return ("start", "continue", "discard")[selected]

    def _resume_loop(self) -> ConfigurationLaunchResult:
        selected = 0
        while True:
            snapshot = self.configuration.snapshot()
            enabled = sum(item.enabled for item in snapshot.mechanisms if item.visible)
            rows = (
                MenuRow(
                    "Resume session",
                    _session_summary(snapshot, enabled),
                ),
                MenuRow(
                    "Review configuration",
                    "Read-only model and component summary",
                ),
                MenuRow("Exit", "Leave without opening the session"),
            )
            self._render(
                title="FruitFlyAgent · resume",
                subtitle="The existing session configuration cannot be changed.",
                rows=rows,
                selected=selected,
            )
            event = self.menu_input.read_event()
            selected, handled = _navigate(event, selected, len(rows))
            if handled:
                continue
            if event.action == MenuAction.QUIT:
                return ConfigurationLaunchResult(start=False)
            if event.action != MenuAction.ACTIVATE:
                continue
            if selected == 0:
                if not snapshot.ready:
                    self.notice = _warnings(snapshot)
                    continue
                return ConfigurationLaunchResult(start=True)
            if selected == 1:
                if self._review_loop(snapshot):
                    return ConfigurationLaunchResult(start=False)
            else:
                return ConfigurationLaunchResult(start=False)

    def _choose_model(self, snapshot: ConfigurationSnapshot) -> bool:
        quit_requested, value = self._choose_value(
            title="Model",
            subtitle="Choose one model from the configured model catalog.",
            values=snapshot.model_profiles,
            current=snapshot.model_profile,
        )
        if value is not _CANCELLED:
            self._call(self.configuration.select_model, str(value))
        return quit_requested

    def _choose_prompt(self, snapshot: ConfigurationSnapshot) -> bool:
        selected = 0
        expanded = set()
        while True:
            snapshot = self.configuration.snapshot()
            labels = dict(snapshot.prompt_option_labels)
            groups = snapshot.prompt_option_groups or (
                ("prompts", "Prompts", snapshot.prompt_options, False),
            )
            rows, actions = [], []
            for group_id, label, references, collapsible in groups:
                if collapsible:
                    current = labels.get(snapshot.prompt_reference) if snapshot.prompt_reference in references else None
                    rows.append(MenuRow(label + (" ▴" if group_id in expanded else " ▾"),
                                        current or f"{len(references)} available", marker="✓" if current else " "))
                    actions.append(("expand", group_id))
                    if group_id not in expanded:
                        continue
                for reference in references:
                    rows.append(MenuRow(("  " if collapsible else "") + labels.get(reference, reference),
                                        "Preview before applying", marker="✓" if reference == snapshot.prompt_reference else " "))
                    actions.append(("prompt", reference))
            rows.append(MenuRow("Back", "Return to configuration"))
            actions.append(("back", None))
            selected = min(selected, len(rows) - 1)
            self._render(title="Base prompt · next session",
                         subtitle="Built-in prompts and task / scenario adaptations. Preview before applying.",
                         rows=tuple(rows), selected=selected)
            event = self.menu_input.read_event()
            selected, handled = _navigate(event, selected, len(rows))
            if handled:
                continue
            if event.action == MenuAction.QUIT:
                return True
            if event.action == MenuAction.BACK:
                return False
            if event.action != MenuAction.ACTIVATE:
                continue
            action, value = actions[selected]
            if action == "back":
                return False
            if action == "expand":
                if value in expanded:
                    expanded.remove(value)
                else:
                    expanded.add(value)
                continue
            try:
                label, content_hash, content = self.configuration.preview_prompt(value)
            except (OSError, TypeError, ValueError) as exc:
                self.notice = f"Could not preview base prompt: {exc}"
                continue
            quit_requested, decision = self._preview_prompt(label, content_hash, content)
            if quit_requested:
                return True
            if decision == "Use for next session":
                self._call(self.configuration.select_prompt, value)
                return False

    def _category_loop(self, category: str) -> bool:
        selected = 0
        expanded = None
        remembered = {}
        while True:
            snapshot = self.configuration.snapshot()
            mechanisms = tuple(item for item in snapshot.mechanisms
                               if item.category == category and item.visible)
            by_id = {item.mechanism_id: item for item in mechanisms}
            groups = [group for group in snapshot.selection_groups
                      if group.category == category and all(option in by_id for option in group.option_ids)]
            grouped_ids = {option for group in groups for option in group.option_ids}
            # Independent capabilities remain composable, with the same inline
            # selector shape as declared groups, even when only one option exists.
            entries = [(group.group_id, group.label, group.option_ids, group.selected_id,
                        group.allow_disabled, True) for group in groups]
            entries += [(item.mechanism_id, item.label, (item.mechanism_id,),
                         item.mechanism_id if item.enabled else None, True, False)
                        for item in mechanisms if item.mechanism_id not in grouped_ids]
            rows = []
            actions = []
            for key, label, options, active, allow_disabled, declared in entries:
                if active is not None:
                    remembered[key] = active
                rows.append(MenuRow(label, marker="✓" if active else " "))
                actions.append(("toggle", key, options, active, allow_disabled, declared))
                if active is not None:
                    rows.append(MenuRow(f"  Algorithm: {by_id[active].label} {'▴' if expanded == key else '▾'}"))
                    actions.append(("expand", key, options, active, allow_disabled, declared))
                    if expanded == key:
                        for option in options:
                            rows.append(MenuRow(f"    {by_id[option].label}", marker="✓" if option == active else " "))
                            actions.append(("choose", key, options, option, allow_disabled, declared))
            rows.append(MenuRow("Back", "Return to configuration"))
            selected = min(selected, len(rows) - 1)
            self._render(title=_category_label(category),
                         subtitle="Check a module, then expand its algorithm dropdown. Changes apply to the next session.",
                         rows=tuple(rows), selected=selected, toggle=True)
            event = self.menu_input.read_event()
            selected, handled = _navigate(event, selected, len(rows))
            if handled:
                continue
            if event.action == MenuAction.QUIT:
                return True
            if event.action == MenuAction.BACK:
                if expanded is not None:
                    selected = next(index for index, action in enumerate(actions)
                                    if action[0] == "expand" and action[1] == expanded)
                    expanded = None
                    continue
                return False
            if event.action not in {MenuAction.ACTIVATE, MenuAction.TOGGLE}:
                continue
            if selected == len(rows) - 1:
                return False
            action, key, options, active, allow_disabled, declared = actions[selected]
            if action == "expand":
                expanded = None if expanded == key else key
                continue
            if action == "toggle":
                if active is not None and not allow_disabled:
                    self.notice = "This module cannot be disabled."
                    continue
                option = None if active is not None else remembered.get(key, options[0])
            else:
                option = active
                selected = next(index for index, action in enumerate(actions)
                                if action[0] == "expand" and action[1] == key)
                expanded = None
            if declared:
                self._call(self.configuration.select_algorithm, key, option)
            else:
                self._call(self.configuration.set_mechanism, key, enabled=option is not None)
            if action == "toggle":
                expanded = None

    def _choose_value(
        self,
        *,
        title: str,
        subtitle: str,
        values: tuple[Any, ...],
        current: Any,
        labels=None,
    ) -> tuple[bool, Any]:
        if not values:
            self.notice = (
                "No models are available. Configure models.yaml and "
                ".fruitfly/config.yaml "
                "before starting a session."
            )
            return False, _CANCELLED
        try:
            selected = values.index(current)
        except ValueError:
            selected = 0
        while True:
            rows = tuple(
                MenuRow(
                    (labels or {}).get(value, str(value)),
                    marker="✓" if value == current else " ",
                )
                for value in values
            )
            self._render(
                title=title,
                subtitle=subtitle,
                rows=rows,
                selected=selected,
            )
            event = self.menu_input.read_event()
            selected, handled = _navigate(event, selected, len(rows))
            if handled:
                continue
            if event.action == MenuAction.QUIT:
                return True, _CANCELLED
            if event.action == MenuAction.BACK:
                return False, _CANCELLED
            if event.action != MenuAction.ACTIVATE:
                continue
            return False, values[selected]

    def _review_loop(self, snapshot: ConfigurationSnapshot) -> bool:
        selected = 0
        categories = _group_mechanisms(snapshot)
        rows = [
            MenuRow("Model", snapshot.model_profile or "Not selected"),
            MenuRow("Base prompt", snapshot.prompt_label),
        ]
        rows.extend(
            MenuRow(_category_label(category), _category_summary(mechanisms))
            for category, mechanisms in categories
        )
        rows.append(MenuRow("Back", "Return to resume"))
        while True:
            self._render(
                title="Configuration summary",
                subtitle=_warnings(snapshot) or "Configuration is valid.",
                rows=tuple(rows),
                selected=selected,
            )
            event = self.menu_input.read_event()
            selected, handled = _navigate(event, selected, len(rows))
            if handled:
                continue
            if event.action == MenuAction.QUIT:
                return True
            if event.action == MenuAction.BACK or selected == len(rows) - 1:
                return False

    def _start(
        self,
        snapshot: ConfigurationSnapshot,
    ) -> ConfigurationLaunchResult | None:
        if not snapshot.ready:
            self.notice = _warnings(snapshot) or "Configuration needs attention."
            return None
        if not snapshot.changed:
            return ConfigurationLaunchResult(start=True)
        try:
            result = self.configuration.save()
        except (OSError, TypeError, ValueError) as exc:
            self.notice = f"Could not save configuration: {exc}"
            return None
        if not result.saved:
            self.notice = result.message or "Configuration was not saved."
            return None
        return ConfigurationLaunchResult(start=True, saved=True)

    def _call(self, function, *args, **kwargs) -> None:
        try:
            result = function(*args, **kwargs)
        except (OSError, TypeError, ValueError) as exc:
            self.notice = f"Configuration error: {exc}"
            return
        self.notice = result.message

    def _render(
        self,
        *,
        title: str,
        subtitle: str,
        rows: tuple[MenuRow, ...],
        selected: int,
        toggle: bool = False,
    ) -> None:
        if self.renderer.ansi:
            instructions = "↑↓ move · Enter select"
            if toggle:
                instructions += " · Space toggle"
            instructions += (
                " · Esc back · q close menu"
                if self._inside_active_session
                else " · Esc back · q quit"
            )
        else:
            instructions = "Enter an option number; blank selects highlighted"
            if toggle:
                instructions += "; type 'space' to toggle"
            instructions += (
                "; q closes the menu"
                if self._inside_active_session
                else "; q quits"
            )
        self.renderer.render(
            title=title,
            subtitle=subtitle,
            rows=rows,
            selected=selected,
            notice=self.notice,
            instructions=instructions,
        )
        self.notice = ""


_CANCELLED = object()


def _navigate(event: MenuEvent, selected: int, size: int) -> tuple[int, bool]:
    if event.index is not None:
        if 0 <= event.index < size:
            return event.index, False
        return selected, True
    if event.action == MenuAction.UP:
        return (selected - 1) % size, True
    if event.action == MenuAction.DOWN:
        return (selected + 1) % size, True
    return selected, False


def _group_mechanisms(
    snapshot: ConfigurationSnapshot,
) -> tuple[tuple[str, tuple[ConfigurationMechanism, ...]], ...]:
    grouped: dict[str, list[ConfigurationMechanism]] = {}
    for mechanism in snapshot.mechanisms:
        if mechanism.visible:
            grouped.setdefault(mechanism.category, []).append(mechanism)
    return tuple(
        (category, tuple(grouped[category])) for category in sorted(grouped)
    )


def _category_label(category: str) -> str:
    return category.replace("-", " ").replace("_", " ").title()


def _category_summary(mechanisms: tuple[ConfigurationMechanism, ...]) -> str:
    enabled = sum(item.enabled for item in mechanisms)
    return f"{enabled} of {len(mechanisms)} enabled"


def _session_summary(snapshot: ConfigurationSnapshot, enabled: int) -> str:
    model = snapshot.model_profile or "model not selected"
    state = "unsaved changes" if snapshot.changed else "saved configuration"
    return f"{model} · {snapshot.prompt_label} (next) · {enabled} components · {state}"


def _warnings(snapshot: ConfigurationSnapshot) -> str:
    return " · ".join(snapshot.warnings)


__all__ = ["TerminalConfigurationFrontend"]
