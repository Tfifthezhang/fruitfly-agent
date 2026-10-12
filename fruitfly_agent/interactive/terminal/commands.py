"""Register asynchronous terminal commands outside the input loop."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from inspect import isawaitable

from fruitfly_agent.interactive.contracts.commands import CommandResult, InteractiveCommand

TerminalCommandHandler = Callable[[InteractiveCommand], CommandResult | Awaitable[CommandResult]]


class TerminalCommandRegistry:
    """Handlers receive parsed commands and capture only their own capabilities."""
    def __init__(self, handlers: Mapping[str, TerminalCommandHandler] | None = None) -> None:
        self._handlers: dict[str, TerminalCommandHandler] = {}
        for name, handler in (handlers or {}).items():
            self.register(name, handler)

    def register(self, name: str, handler: TerminalCommandHandler, *, replace: bool = False) -> None:
        if not name or name != name.lower() or any(c.isspace() or c in "/\\" for c in name):
            raise ValueError("command name must be one lowercase token")
        if name in self._handlers and not replace:
            raise ValueError(f"terminal command already registered: {name}")
        if not callable(handler):
            raise TypeError("command handler must be callable")
        self._handlers[name] = handler

    async def execute(self, command: InteractiveCommand) -> CommandResult | None:
        handler = self._handlers.get(command.name)
        if handler is None:
            return None
        value = handler(command)
        result = await value if isawaitable(value) else value
        if not isinstance(result, CommandResult):
            raise TypeError("terminal command handler must return CommandResult")
        return result
