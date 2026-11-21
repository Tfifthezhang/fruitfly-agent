"""Terminal-local view actions; no application commands or runtime state."""
from enum import Enum
from functools import wraps
from typing import Callable, ParamSpec, TypeVar


class InputEnded(EOFError):
    """The terminal input stream ended; never an explicit discard action."""


_P = ParamSpec("_P")
_T = TypeVar("_T")


def cancellable_form(function: Callable[_P, _T]) -> Callable[_P, _T | bool]:
    """Cancel a local form without interpreting EOF as a user choice."""
    @wraps(function)
    def run(*args: _P.args, **kwargs: _P.kwargs) -> _T | bool:
        try:
            return function(*args, **kwargs)
        except (InputInterrupted, KeyboardInterrupt):
            return False
    return run


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
