"""Terminal-local view actions; no application commands or runtime state."""
from enum import Enum


class InputInterrupted(Exception):
    """An editor control key; never a process-level KeyboardInterrupt."""

    def __init__(self, *, handled: bool = False) -> None:
        super().__init__('input interrupted')
        self.handled = handled


class ViewAction(Enum):
    PAGE_UP = 'page_up'
    PAGE_DOWN = 'page_down'
    LATEST = 'latest'
    WHEEL_UP = 'wheel_up'
    WHEEL_DOWN = 'wheel_down'
    TOGGLE_COPY = 'toggle_copy'
    TOGGLE_MOUSE = 'toggle_mouse'
    EXIT_COPY = 'exit_copy'


_KEYS = {
    b'\x1b[5~': ViewAction.PAGE_UP, b'\x1b[5;2~': ViewAction.PAGE_UP,
    b'\x1b[6~': ViewAction.PAGE_DOWN, b'\x1b[6;2~': ViewAction.PAGE_DOWN,
    b'\x1b[1;5F': ViewAction.LATEST, b'\x1b[4;5~': ViewAction.LATEST,
    b'\x1bOQ': ViewAction.TOGGLE_COPY, b'\x1b[12~': ViewAction.TOGGLE_COPY,
    b'\x1bOR': ViewAction.TOGGLE_MOUSE, b'\x1b[13~': ViewAction.TOGGLE_MOUSE,
    b'\x1b': ViewAction.EXIT_COPY,
}


def view_action(sequence: bytes) -> ViewAction | None:
    if sequence.startswith(b'\x1b[<64;'):
        return ViewAction.WHEEL_UP
    if sequence.startswith(b'\x1b[<65;'):
        return ViewAction.WHEEL_DOWN
    return _KEYS.get(sequence)
