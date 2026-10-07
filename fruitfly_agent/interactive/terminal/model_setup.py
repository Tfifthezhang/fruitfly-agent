"""Generic model form and secret input; the injected host owns persistence."""

import termios

from ..model_setup import ModelSetupService
from .input import read_field_line
from .menu import MenuAction, MenuRow, navigate_menu


def read_secret(input_stream, output_stream) -> str | None:
    """Bypass readline/history and disable TTY echo, restoring it on every exit."""
    descriptor = input_stream.fileno() if input_stream.isatty() else None
    original = termios.tcgetattr(descriptor) if descriptor is not None else None
    try:
        if original is not None:
            hidden = list(original)
            hidden[3] &= ~(termios.ECHO | termios.ECHONL)
            termios.tcsetattr(descriptor, termios.TCSANOW, hidden)
        output_stream.write("API key (hidden; blank reuses an existing key): ")
        output_stream.flush()
        line = input_stream.readline()
        return None if line == "" else line.rstrip("\r\n")
    finally:
        if original is not None:
            termios.tcsetattr(descriptor, termios.TCSADRAIN, original)
        output_stream.write("\n")
        output_stream.flush()


def run_model_setup(frontend, service: ModelSetupService) -> None:
    options = service.options()
    quit_requested, chosen = frontend._choose_value(
        title="Add model · Choose a service", subtitle=(
            "Use an official service or a compatible gateway / self-hosted server.\n"
            "For custom services, check which API protocol your service supports.\n"
            "Streaming and tool calls are required. Chat Completions-only services are unsupported."
        ),
        values=tuple(option.option_id for option in options), current=None,
        labels={option.option_id: option.label for option in options},
        details={option.option_id: option.description for option in options},
    )
    option = next((option for option in options if option.option_id == chosen), None)
    if quit_requested or option is None:
        return
    values = {field.name: str(field.value) for field in option.fields if field.kind == "constant"}
    text_fields = tuple(field for field in option.fields if field.kind not in ("bool", "constant"))
    bool_fields = tuple(field for field in option.fields if field.kind == "bool")
    total = len(text_fields) + bool(bool_fields) + 1
    for step, field in enumerate(text_fields, 1):
        default = str(field.value or "")
        _render_field(frontend, option.label, step, total, field.label, field.description,
                      f"Press Enter to use: {default}" if default else "")
        line = read_field_line(frontend.line_editor, field.label)
        if line is None or line.strip() == "/cancel":
            return
        values[field.name] = line.strip() or default
    if bool_fields:
        selected = _capabilities(frontend, option.label, bool_fields, len(text_fields) + 1, total)
        if selected is None:
            return
        values.update(selected)
    _render_field(frontend, option.label, total, total, "API key",
                  "Enter your service's API key. Input is hidden and excluded from history.",
                  "Leave blank only when reusing an existing key.")
    secret = read_secret(frontend.input, frontend.output)
    if secret is None or secret == "/cancel":
        return
    _, action = frontend._choose_value(
        title="Add model · Review", subtitle=f"Service: {option.label}\n" + "\n".join(f"{field.name if field.kind == 'bool' else field.label}: {values[field.name] or '(default)'}" for field in option.fields)
            + "\nAPI key: entered or reused (value hidden)\nOffline checks only; changes remain staged until saved.",
        values=("Cancel", "Stage model"), current="Cancel",
    )
    if action == "Stage model":
        frontend._call(service.stage, option.option_id, values, secret)


def configure_credential(frontend, service: ModelSetupService, model_profile: str) -> None:
    _render_field(frontend, model_profile, 1, 1, "API key",
                  "Enter the key for this model. Input is hidden and excluded from history.", "",
                  title="Set API key", context="Model")
    secret = read_secret(frontend.input, frontend.output)
    if secret is None or secret == "/cancel":
        return
    _, action = frontend._choose_value(
        title="API key", subtitle="Value hidden. Save configuration to apply to a new session.",
        values=("Cancel", "Stage API key"), current="Cancel",
    )
    if action == "Stage API key":
        frontend._call(service.stage_credential, model_profile, secret)


def _capabilities(frontend, service_label, fields, step, total):
    values = {field.name: bool(field.value) for field in fields}
    selected = len(fields)
    notice = ""
    while True:
        rows = tuple(MenuRow(field.label, field.description + (" · required" if len(field.choices) == 1 else ""),
                             marker="✓" if values[field.name] else " ") for field in fields)
        frontend.renderer.render(title=f"Add model · Step {step} of {total} · capabilities",
            subtitle=f"Service: {service_label}\nChecked = true; unchecked = false. Choose capabilities your service supports.",
            rows=rows + (MenuRow("Continue", "Keep these capabilities"),), selected=selected, notice=notice,
            instructions=("↑↓ move · Space / Enter toggle · Continue to confirm · Esc / q cancel"
                          if frontend.renderer.ansi else f"Enter a number to toggle; choose {len(fields) + 1} to continue (blank selects highlighted). 'back' / q cancels."))
        event = frontend.menu_input.read_event()
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


def _render_field(frontend, service_label, step, total, label, description, default_hint,
                  *, title="Add model", context="Service"):
    frontend.renderer.render(
        title=f"{title} · Step {step} of {total}",
        subtitle=f"{context}: {service_label}\n\n{label}\n{description}"
                 + (f"\n{default_hint}" if default_hint else ""),
        rows=(), selected=0,
        instructions="Enter to continue · /cancel to return without changes. Nothing is saved yet.",
    )
