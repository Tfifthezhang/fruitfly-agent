"""Provider-free, option-driven startup configuration center."""

from __future__ import annotations

import sys
from dataclasses import replace
from typing import Any, Callable, Mapping, TextIO

from fruitfly_agent.interactive.contracts.configuration import (
    ConfigurationController,
    ConfigurationActionResult,
    ConfigurationLaunchResult,
    ConfigurationMechanism,
    ConfigurationSnapshot,
)
from fruitfly_agent.interactive.terminal.io.input import LineEditor, create_line_editor, read_field_line, field_prompt, parse_field_value
from fruitfly_agent.interactive.terminal.io.live import InputInterrupted
from fruitfly_agent.interactive.terminal.features.configuration.model_setup import (
    configure_credential,
    run_model_setup,
)
from .mechanism_setup import run_mechanism_setup
from .presentation import category_rows, has_settings, settings_rows
from .forms import FormIO, CANCELLED as _CANCELLED, choose_value, select_field
from fruitfly_agent.interactive.terminal.io.menu import (
    MenuAction,
    MenuInput,
    LineMenuInput,
    MenuRow,
    MenuHelp,
    TerminalMenuRenderer,
    create_menu_input,
    navigate_menu,
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
        self.renderer.numbered = isinstance(self.menu_input, LineMenuInput)
        self.notice = ""
        self._inside_active_session = False

    def run(self, *, configure: bool = False) -> ConfigurationLaunchResult:
        """Start directly when ready; lend input only for requested edits or repair."""
        snapshot = self.configuration.snapshot()
        if getattr(self.configuration, 'read_only', False):
            if configure or not snapshot.ready:
                if self._review_loop(snapshot):
                    return ConfigurationLaunchResult(start=False)
            return ConfigurationLaunchResult(start=snapshot.ready)
        if configure:
            return self._configure_startup_loop()
        if not self._repair_startup():
            if self.notice:
                return self._configure_startup_loop()
            self.configuration.reset()
            return ConfigurationLaunchResult(start=False)
        repaired = self.configuration.snapshot()
        if not snapshot.ready and repaired.ready and repaired.changed:
            decision = self._confirm_application(startup=True)
            if decision == 'discard':
                self.configuration.reset()
                return ConfigurationLaunchResult(start=False)
            if decision == 'continue':
                return self._configure_startup_loop()
        result = self._start(repaired)
        if result is None and snapshot.ready:
            raise ValueError(self.notice)
        return result if result is not None else self._configure_startup_loop()

    def _repair_startup(self) -> bool:
        """Use host-supplied forms for missing model and enabled-component inputs."""
        setup = getattr(self.configuration, 'model_setup', None)
        snapshot = self.configuration.snapshot()
        if setup is not None and not snapshot.model_profiles:
            run_model_setup(self._model_form(), setup)
            snapshot = self.configuration.snapshot()
            if not snapshot.model_profiles:
                return False
        if snapshot.model_profiles and snapshot.model_profile not in snapshot.model_profiles:
            if self._choose_model(snapshot):
                return False
            snapshot = self.configuration.snapshot()
            if snapshot.model_profile not in snapshot.model_profiles:
                return False
        if setup is not None and snapshot.model_profile is not None:
            if setup.credential_status(snapshot.model_profile) == 'API key missing':
                configure_credential(self._model_form(), setup, snapshot.model_profile)
                if setup.credential_status(snapshot.model_profile) == 'API key missing':
                    return False
        service = getattr(self.configuration, 'mechanism_setup', None)
        if service is not None:
            for mechanism in self.configuration.snapshot().mechanisms:
                if mechanism.enabled and mechanism.setup_available and not service.ready(mechanism.mechanism_id):
                    if not run_mechanism_setup(self._model_form(), service, mechanism.mechanism_id):
                        return False
        return True

    def _configure_startup_loop(self) -> ConfigurationLaunchResult:
        while True:
            if self._configure_loop(back_detail='Review settings before starting'):
                self.configuration.reset()
                return ConfigurationLaunchResult(start=False)
            if not self._repair_startup():
                self.configuration.reset()
                return ConfigurationLaunchResult(start=False)
            snapshot = self.configuration.snapshot()
            if not snapshot.ready:
                self.notice = _warnings(snapshot) or 'Configuration needs attention.'
                continue
            if snapshot.changed:
                decision = self._confirm_application(startup=True)
                if decision == 'continue':
                    continue
                if decision == 'discard':
                    self.configuration.reset()
                    return ConfigurationLaunchResult(start=False)
            result = self._start(snapshot)
            if result is not None:
                return result

    def run_for_active_session(self) -> ConfigurationLaunchResult:
        """Return draft application intent; the host owns saving and assembly."""
        self._inside_active_session = True
        try:
            if getattr(self.configuration, "read_only", False):
                self._review_loop(self.configuration.snapshot())
                return ConfigurationLaunchResult(start=False)
            while True:
                self._configure_loop(back_detail="Review changes before returning")
                snapshot = self.configuration.snapshot()
                if not snapshot.changed:
                    return ConfigurationLaunchResult(start=False)
                decision = self._confirm_application()
                if decision == "continue":
                    continue
                if decision == "discard":
                    try:
                        self.configuration.reset()
                    except (OSError, TypeError, ValueError) as exc:
                        self.notice = f"Could not discard configuration: {exc}"
                        continue
                    return ConfigurationLaunchResult(start=False)
                return ConfigurationLaunchResult(start=True)
        finally:
            self._inside_active_session = False

    def _preview_prompt(self, label: str, content_hash: str, content: str) -> tuple[bool, object]:
        """Preview complete prompt text before staging a configuration choice."""
        import textwrap
        lines = [part for line in content.splitlines()
                 for part in (textwrap.wrap(line, width=80, replace_whitespace=False) or [''])]
        page, selected, size = 0, 1, 8
        values = ('Use this prompt', 'Back')
        while True:
            self._render(title='prompt · preview',
                subtitle=f'{label} · {content_hash}\nReview prompt ({page + 1}/{max(1, (len(lines) + size - 1)//size)})\n'
                         + '\n'.join(lines[page*size:(page+1)*size])
                         + '\nPageUp/PageDown: text pages',
                rows=tuple(MenuRow(value) for value in values), selected=selected, help_panel=False)
            event = self.menu_input.read_event()
            selected, handled = navigate_menu(event, selected, len(values))
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
        back_detail: str = "Review settings before starting",
    ) -> bool:
        if getattr(self.configuration, "read_only", False):
            self._review_loop(self.configuration.snapshot())
            return False
        selected = 0
        while True:
            snapshot = self.configuration.snapshot()
            categories = _group_mechanisms(snapshot)
            rows = [
                MenuRow("model", snapshot.model_profile or "Select a model",
                    help=MenuHelp('Model', 'Select a model or configure its connection.')),
                MenuRow("prompt", f"{snapshot.prompt_label} · draft",
                    help=MenuHelp('Prompt', 'Preview an instruction before selecting it.')),
            ]
            rows.extend(
                MenuRow(
                    _category_label(category),
                    _category_summary(mechanisms),
                    help=MenuHelp(_category_label(category), 'Choose components and their settings.'),
                )
                for category, mechanisms in categories
            )
            restore = getattr(self.configuration, "restore_defaults", None)
            if restore is not None:
                rows.append(MenuRow("Restore default configuration", help=MenuHelp("Restore default configuration", "Stage default harness settings; keep model and credentials")))
            rows.append(MenuRow("Back", help=MenuHelp("Back", back_detail)))
            selected = min(selected, len(rows) - 1)
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
            selected, handled = navigate_menu(event, selected, len(rows))
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
            elif restore is not None:
                self._call(restore)

    def _confirm_application(self, *, startup: bool = False) -> str:
        selected = 0
        rows = (
            MenuRow("Save and start" if startup else "Save and apply to this conversation"),
            MenuRow("Continue configuring", help=MenuHelp("Continue configuring", "Return to the configuration menu")),
            MenuRow(
                "Discard changes",
                help=MenuHelp("Discard changes", "Exit without saving" if startup else "Keep using the current session and its existing configuration"),
            ),
        )
        while True:
            self._render(
                title="Start session" if startup else "Apply configuration",
                subtitle="Save the selected settings and start chatting." if startup else "Apply the selected settings and continue this conversation.",
                rows=rows,
                selected=selected,
            )
            event = self.menu_input.read_event()
            selected, handled = navigate_menu(event, selected, len(rows))
            if handled:
                continue
            if event.action == MenuAction.BACK:
                return "continue"
            if event.action == MenuAction.QUIT:
                return "discard"
            if event.action != MenuAction.ACTIVATE:
                continue
            return ("apply", "continue", "discard")[selected]

    def _model_form(self) -> FormIO:
        return FormIO(
            choose_value=self._choose_value, apply=self._call, line_editor=self.line_editor,
            menu_input=self.menu_input, renderer=self.renderer, input=self.input, output=self.output,
        )

    def _choose_model(self, snapshot: ConfigurationSnapshot) -> bool:
        setup = getattr(self.configuration, "model_setup", None)
        if setup is not None:
            values = snapshot.model_profiles + ("Add model…", "Set API key…")
            labels = {name: f"{name} · {setup.credential_status(name)}" for name in snapshot.model_profiles}
            quit_requested, value = self._choose_value(
                title="model.profile", subtitle="Choose a model or add one. Review and save before applying changes.",
                values=values, current=snapshot.model_profile, labels=labels,
            )
            if value == "Add model…":
                run_model_setup(self._model_form(), setup)
            elif value == "Set API key…":
                if snapshot.model_profile is None:
                    self.notice = "Select a model before setting its API key."
                else:
                    configure_credential(self._model_form(), setup, snapshot.model_profile)
            elif value is not _CANCELLED:
                self._call(self.configuration.select_model, str(value))
            return quit_requested
        quit_requested, value = self._choose_value(
            title="model.profile",
            subtitle="Choose one model from the configured model catalog.",
            values=snapshot.model_profiles,
            current=snapshot.model_profile,
        )
        if value is not _CANCELLED:
            self._call(self.configuration.select_model, str(value))
        return quit_requested

    def _choose_prompt(self, snapshot: ConfigurationSnapshot) -> bool:
        selected = 0
        expanded: set[str] = set()
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
                                        help=MenuHelp(labels.get(reference, reference), "Preview before applying"), marker="✓" if reference == snapshot.prompt_reference else " "))
                    actions.append(("prompt", reference))
            rows.append(MenuRow("Back", help=MenuHelp("Back", "Return to configuration")))
            actions.append(("back", ""))
            selected = min(selected, len(rows) - 1)
            self._render(title="prompt · draft",
                         subtitle="Built-in prompts and task / scenario adaptations. Preview before applying.",
                         rows=tuple(rows), selected=selected)
            event = self.menu_input.read_event()
            selected, handled = navigate_menu(event, selected, len(rows))
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
            if decision == "Use this prompt":
                self._call(self.configuration.select_prompt, value)
                return False

    def _category_loop(self, category: str) -> bool:
        selected = 0
        expanded: str | None = None
        remembered: dict[str, str] = {}
        original = self.configuration.snapshot()
        focus: tuple[str, str, str] | None = None
        while True:
            snapshot = self.configuration.snapshot()
            rows, actions = category_rows(snapshot, category, expanded, original=original)
            for action in actions:
                if action.kind == 'expand' and action.active is not None:
                    remembered[action.key] = action.active
            identities = [action.identity for action in actions]
            selected = identities.index(focus) if focus in identities else min(selected, len(rows) - 1)
            focused_action = actions[selected]
            activate = 'select'
            if focused_action.kind == 'expand':
                activate = 'expand' if len(focused_action.options) > 1 else 'settings'
            self._render(title=_category_label(category),
                         subtitle='Choose runtime components.' + (' Unsaved changes.' if snapshot.changed else ''),
                         rows=tuple(rows), selected=selected, toggle=focused_action.kind == 'expand', activate=activate)
            event = self.menu_input.read_event()
            selected, handled = navigate_menu(event, selected, len(rows))
            focus = actions[selected].identity
            if handled:
                continue
            if event.action == MenuAction.QUIT:
                return True
            if event.action == MenuAction.BACK:
                if expanded is not None:
                    focus = ('expand', expanded, '')
                    expanded = None
                    continue
                return False
            if event.action not in {MenuAction.ACTIVATE, MenuAction.TOGGLE}:
                continue
            if selected == len(rows) - 1 and event.action == MenuAction.ACTIVATE:
                return False
            action = actions[selected]
            if event.action == MenuAction.ACTIVATE and action.kind == 'expand':
                if len(action.options) > 1:
                    expanded = None if expanded == action.key else action.key
                else:
                    item = next(item for item in snapshot.mechanisms if item.mechanism_id == action.options[0])
                    if has_settings(item) and self._settings_loop(item.mechanism_id, original):
                        return True
                continue
            if event.action == MenuAction.ACTIVATE and action.kind == 'settings':
                if self._settings_loop(action.active, original):
                    return True
                continue
            if event.action == MenuAction.TOGGLE and action.kind != 'expand':
                continue
            active = next(a.active for a in actions if a.kind == 'expand' and a.key == action.key)
            if event.action == MenuAction.TOGGLE:
                if active is not None and not action.allow_disabled:
                    self.notice = "This module cannot be disabled."
                    continue
                option = None if active is not None else remembered.get(action.key, action.options[0])
            else:
                option = action.active
            service = getattr(self.configuration, 'mechanism_setup', None)
            chosen = next((item for item in snapshot.mechanisms if item.mechanism_id == option), None)
            if (option is not None and service is not None and chosen is not None
                    and chosen.setup_available and not service.ready(option)):
                run_mechanism_setup(self._model_form(), service, option)
                focus = ('expand', action.key, '')
                continue
            if action.declared:
                self._call(self.configuration.select_algorithm, action.key, option)
            else:
                self._call(self.configuration.set_mechanism, action.key, enabled=option is not None)
            focus = action.identity

    def _settings_loop(self, mechanism_id: str | None, original: ConfigurationSnapshot) -> bool:
        selected = 0
        focus: tuple[str, str, str] | None = None
        while True:
            snapshot = self.configuration.snapshot()
            current = next((item for item in snapshot.mechanisms if item.mechanism_id == mechanism_id), None)
            if current is None:
                return False
            rows, actions = settings_rows(current, original=original)
            identities = [action.identity for action in actions]
            selected = identities.index(focus) if focus in identities else min(selected, len(rows) - 1)
            self._render(title=current.label, subtitle='', rows=tuple(rows), selected=selected)
            event = self.menu_input.read_event()
            selected, handled = navigate_menu(event, selected, len(rows))
            focus = actions[selected].identity
            if handled:
                continue
            if event.action == MenuAction.QUIT:
                return True
            if event.action == MenuAction.BACK:
                return False
            if event.action != MenuAction.ACTIVATE:
                continue
            action = actions[selected]
            if action.kind == 'back':
                return False
            if event.action == MenuAction.ACTIVATE and action.kind == 'parameter':
                spec = action.parameter
                assert spec is not None
                try:
                    if spec.choices:
                        choice = select_field(self._model_form(), title=spec.label, description=spec.description,
                            choices=spec.choices, current=spec.value)
                        if choice is not _CANCELLED:
                            self._call(self.configuration.set_parameter, action.active, spec.name, str(choice))
                    else:
                        self.renderer.begin_input(field_prompt(spec, spec.value), selected=selected)
                        value = read_field_line(self.line_editor, spec.label)
                        if value is not None and value.strip() and value.strip() != '/cancel':
                            parse_field_value(spec, value)
                            self._call(self.configuration.set_parameter, action.active, spec.name,
                                '' if value.strip() == '/clear' else value.strip())
                except (InputInterrupted, KeyboardInterrupt):
                    pass
                except ValueError as exc:
                    self.notice = f'Invalid parameter: {exc}'
                continue
            if event.action == MenuAction.ACTIVATE and action.kind == 'setup':
                service = getattr(self.configuration, 'mechanism_setup', None)
                if service is not None and action.active is not None:
                    run_mechanism_setup(self._model_form(), service, action.active)
                continue

    def _choose_value(
        self,
        *,
        title: str,
        subtitle: str,
        values: tuple[Any, ...],
        current: Any,
        labels: Mapping[str, str] | None = None,
        details: Mapping[str, str] | None = None,
    ) -> tuple[bool, Any]:
        notice, self.notice = self.notice, ''
        return choose_value(self.menu_input, self.renderer, title=title, subtitle=subtitle,
            values=values, current=current, labels=labels, details=details, notice=notice)

    def _review_loop(self, snapshot: ConfigurationSnapshot) -> bool:
        selected = 0
        categories = _group_mechanisms(snapshot)
        rows = [
            MenuRow("model.profile", snapshot.model_profile or "Not selected"),
            MenuRow("prompt", snapshot.prompt_label),
        ]
        rows.extend(
            MenuRow(_category_label(category), _category_summary(mechanisms))
            for category, mechanisms in categories
        )
        rows.append(MenuRow("Back", help=MenuHelp("Back", "Return from configuration review")))
        while True:
            self._render(
                title="Configuration summary",
                subtitle=_warnings(snapshot) or "Configuration is valid.",
                rows=tuple(rows),
                selected=selected,
            )
            event = self.menu_input.read_event()
            selected, handled = navigate_menu(event, selected, len(rows))
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
        setup = getattr(self.configuration, "model_setup", None)
        if setup is not None and snapshot.model_profile is not None and setup.credential_status(snapshot.model_profile) == "API key missing":
            self.notice = "API key missing. Open Configure → model → Set API key…"
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

    def _call(
        self, function: Callable[..., ConfigurationActionResult], *args: object, **kwargs: object,
    ) -> ConfigurationActionResult | None:
        try:
            result = function(*args, **kwargs)
        except (OSError, TypeError, ValueError) as exc:
            self.notice = f"Configuration error: {exc}"
            return None
        self.notice = result.message
        return result

    def _render(
        self,
        *,
        title: str,
        subtitle: str,
        rows: tuple[MenuRow, ...],
        selected: int,
        toggle: bool = False,
        activate: str = 'select',
        help_panel: bool = True,
    ) -> None:
        if self.renderer.ansi and not self.renderer.numbered:
            instructions = f"↑↓ move · Enter {activate}"
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
            help_panel=help_panel,
        )
        self.notice = ""





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
    return 'Context' if category == 'context-manager' else category.replace('-', ' ').capitalize()


def _category_summary(mechanisms: tuple[ConfigurationMechanism, ...]) -> str:
    enabled = sum(item.enabled for item in mechanisms)
    return f"{enabled} of {len(mechanisms)} enabled"


def _warnings(snapshot: ConfigurationSnapshot) -> str:
    return " · ".join(snapshot.warnings)


__all__ = ["TerminalConfigurationFrontend"]
