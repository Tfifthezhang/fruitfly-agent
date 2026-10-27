"""Generic model form and secret input; the injected host owns persistence."""

import json
import os
import shutil
import textwrap

from fruitfly_agent.interactive.terminal.io.input import LineEditor

from .forms import FormIO, CANCELLED, select_field
from fruitfly_agent.interactive.terminal.io.secret import read_secret
from fruitfly_agent.interactive.contracts.model_setup import ModelSetupOption, ModelSetupService
from fruitfly_agent.interactive.terminal.io.input import read_field_line
from fruitfly_agent.interactive.terminal.io.menu import MenuAction, MenuRow, navigate_menu


def run_model_setup(form: FormIO, service: ModelSetupService) -> None:
    option = _choose_service(form, service.options())
    if option is None:
        return
    values = {field.name: str(field.value) for field in option.fields if field.kind == "constant"}
    text_fields = tuple(field for field in option.fields if field.kind not in ("bool", "constant"))
    bool_fields = tuple(field for field in option.fields if field.kind == "bool")
    total = len(text_fields) + bool(bool_fields) + 1
    for step, field in enumerate(text_fields, 1):
        if field.kind == 'choice':
            field = service.field(option.option_id, field.name, values)
        default = str(field.value or "")
        _render_field(form, option.label, step, total, field.label, field.description,
                      f"Press Enter to use: {default}" if default else "")
        if field.kind == 'choice' or field.choices:
            choice = select_field(form, title=f'Add model · {field.label}', description=field.description,
                choices=field.choices, current=field.value)
            if choice is CANCELLED:
                return
            values[field.name] = str(choice)
            continue
        line = read_field_line(form.line_editor, field.label)
        if line is None or line.strip() == "/cancel":
            return
        values[field.name] = line.strip() or default
    if bool_fields:
        selected = _capabilities(form, option.label, bool_fields, len(text_fields) + 1, total)
        if selected is None:
            return
        values.update(selected)
    _render_field(form, option.label, total, total, "API key",
                  "Enter your service's API key. Input is hidden and excluded from history.",
                  "Leave blank only when reusing an existing key.")
    secret = read_secret(form.input, form.output)
    if secret is None or secret == "/cancel":
        return
    defaults = json.dumps(service.defaults(option.option_id, values), ensure_ascii=False, indent=2)
    action = _review(form, f"Service: {option.label}\n" + "\n".join(f"{field.name if field.kind == 'bool' else field.label}: {values[field.name] or '(default)'}" for field in option.fields)
            + "\nRequest and transport defaults (confirm to save):\n" + defaults
            + "\nEmpty parameters use service defaults; capabilities alone do not enable thinking."
            + "\nAPI key: entered or reused (value hidden)\nOffline checks only; changes remain staged until saved.",
    )
    if action == "Stage model":
        form.apply(service.stage, option.option_id, values, secret)


def _choose_service(form: FormIO, options: tuple[ModelSetupOption, ...]) -> ModelSetupOption | None:
    groups: dict[str, list[ModelSetupOption]] = {}
    for option in options:
        groups.setdefault(option.group, []).append(option)
    while True:
        quit_requested, group = form.choose_value(title="Add model · Choose a service",
            subtitle="Select the service your API key belongs to.\n"
                     "Presets supply API defaults; custom services open protocol choices.",
            values=tuple(groups), current=None,
            details={name: items[0].description if len(items) == 1 else
                     "Choose the API protocol supported by your gateway or server."
                     for name, items in groups.items()})
        if quit_requested or group is CANCELLED:
            return None
        items = groups[group]
        if len(items) == 1:
            return items[0]
        quit_requested, chosen = form.choose_value(title=f"Add model · {group} · Choose API protocol",
            subtitle="Use the protocol documented by your service. Streaming and tool calls are required.\n"
                     "Back returns to service selection.",
            values=tuple(item.option_id for item in items), current=None,
            labels={item.option_id: item.label for item in items},
            details={item.option_id: item.description for item in items})
        if quit_requested:
            return None
        if chosen is not CANCELLED:
            return next(item for item in items if item.option_id == chosen)


def _review(form: FormIO, text: str):
    """Keep every reviewed default reachable on a short ANSI terminal."""
    if not form.renderer.ansi:
        return form.choose_value(title="Add model · Review", subtitle=text,
            values=("Cancel", "Stage model"), current="Cancel")[1]
    try:
        size = os.get_terminal_size(form.output.fileno())
    except (AttributeError, OSError, ValueError):
        size = shutil.get_terminal_size(fallback=(80, 24))
    width, count = max(16, size.columns - 2), max(1, size.lines - 14)
    lines = [part for line in text.splitlines() for part in (textwrap.wrap(line, width) or [''])]
    pages = [lines[start:start + count] for start in range(0, len(lines), count)]
    page = 0
    while True:
        quit_requested, action = form.choose_value(title="Add model · Review",
            subtitle=f"Review {page + 1}/{len(pages)} · Next/Previous to inspect all values\n" + '\n'.join(pages[page]),
            values=("Cancel", "Stage model", "Next page", "Previous page"), current="Cancel")
        if quit_requested or action not in ("Next page", "Previous page"):
            return action
        page = (page + (1 if action == "Next page" else -1)) % len(pages)


def configure_credential(form: FormIO, service: ModelSetupService, model_profile: str) -> None:
    _render_field(form, model_profile, 1, 1, "API key",
                  "Enter the key for this model. Input is hidden and excluded from history.", "",
                  title="Set API key", context="Model")
    secret = read_secret(form.input, form.output)
    if secret is None or secret == "/cancel":
        return
    _, action = form.choose_value(
        title="API key", subtitle="Value hidden. Save configuration before applying settings.",
        values=("Cancel", "Stage API key"), current="Cancel",
    )
    if action == "Stage API key":
        form.apply(service.stage_credential, model_profile, secret)


def _capabilities(form, service_label, fields, step, total):
    values = {field.name: bool(field.value) for field in fields}
    selected = len(fields)
    notice = ""
    while True:
        rows = tuple(MenuRow(field.label, field.description + (" · required" if len(field.choices) == 1 else ""),
                             marker="✓" if values[field.name] else " ") for field in fields)
        form.renderer.render(title=f"Add model · Step {step} of {total} · capabilities",
            subtitle=f"Service: {service_label}\nChecked = true; unchecked = false. Choose capabilities your service supports.",
            rows=rows + (MenuRow("Continue", "Keep these capabilities"),), selected=selected, notice=notice,
            instructions=("↑↓ move · Space / Enter toggle · Continue to confirm · Esc / q cancel"
                          if form.renderer.ansi else f"Enter a number to toggle; choose {len(fields) + 1} to continue (blank selects highlighted). 'back' / q cancels."))
        event = form.menu_input.read_event()
        if event.action in (MenuAction.BACK, MenuAction.QUIT):
            return None
        selected, handled = navigate_menu(event, selected, len(rows) + 1)
        if handled or event.action not in (MenuAction.ACTIVATE, MenuAction.TOGGLE):
            continue
        if selected == len(fields):
            if event.action == MenuAction.ACTIVATE:
                return {name: str(value).lower() for name, value in values.items()}
            continue
        field = fields[selected]
        candidate = not values[field.name]
        if field.choices and candidate not in field.choices:
            notice = f"{field.label} is required by this harness."
        else:
            values[field.name] = candidate
            notice = ""


def _render_field(form, service_label, step, total, label, description, default_hint,
                  *, title="Add model", context="Service"):
    form.renderer.render(
        title=f"{title} · Step {step} of {total}",
        subtitle=f"{context}: {service_label}\n\n{label}\n{description}"
                 + (f"\n{default_hint}" if default_hint else ""),
        rows=(), selected=0,
        instructions="Enter to continue · /cancel to return without changes. Nothing is saved yet.",
    )
