"""Shared configuration form operations; independent of model and mechanism flows."""
from dataclasses import dataclass
from typing import Any, Callable, Mapping, TextIO
from fruitfly_agent.interactive.terminal.io.input import LineEditor
from fruitfly_agent.interactive.terminal.io.menu import MenuInput, TerminalMenuRenderer, MenuRow, MenuHelp, MenuAction, navigate_menu

CANCELLED = object()

@dataclass(frozen=True)
class FormIO:
    """Explicit menu, rendering, and staging operations used by configuration forms."""
    choose_value: Callable
    apply: Callable
    line_editor: LineEditor
    menu_input: MenuInput
    renderer: TerminalMenuRenderer
    input: TextIO
    output: TextIO



def choose_value(menu_input: MenuInput, renderer: TerminalMenuRenderer, *, title: str,
                 subtitle: str, values: tuple[Any, ...], current: Any,
                 labels: Mapping[Any, str] | None = None,
                 details: Mapping[Any, str] | None = None,
                 notice: str = '') -> tuple[bool, Any]:
    """Select the original value; cancellation is distinct from any field value."""
    if not values:
        return False, CANCELLED
    try:
        selected = values.index(current)
    except ValueError:
        selected = 0
    while True:
        rows = tuple(MenuRow((labels or {}).get(value, str(value)),
            help=MenuHelp((labels or {}).get(value, str(value)), (details or {}).get(value, '')), marker='✓' if value == current else ' ')
            for value in values)
        renderer.render(title=title, subtitle=subtitle, rows=rows, selected=selected,
            notice=notice, help_panel=bool(details),
            instructions=('↑↓ move · Enter select · Esc / q cancel' if not renderer.numbered
                else 'Enter a number to select; blank keeps the highlighted choice. back / q cancels.'))
        notice = ''
        event = menu_input.read_event()
        selected, handled = navigate_menu(event, selected, len(rows))
        if handled:
            continue
        if event.action == MenuAction.QUIT:
            return True, CANCELLED
        if event.action == MenuAction.BACK:
            return False, CANCELLED
        if event.action == MenuAction.ACTIVATE:
            return False, values[selected]


def select_field(form: FormIO, *, title: str, description: str,
                 choices: tuple[object, ...], current: object) -> object:
    quit_requested, value = form.choose_value(title=title, subtitle=description,
        values=choices, current=current)
    return CANCELLED if quit_requested else value
