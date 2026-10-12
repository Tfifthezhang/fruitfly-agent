"""Compose host commit hooks around a prepared handle's activation callback."""
from typing import Callable
from fruitfly_agent.interactive.application import RuntimeHandle


def bind_activation(handle: RuntimeHandle, *, before: Callable[[], None],
                    after: Callable[[], None] | None = None) -> None:
    original = handle.activate_callback

    def activate():
        before()
        if original is not None:
            original()
        if after is not None:
            after()

    handle.activate_callback = activate
