"""Register asynchronous terminal commands outside the input loop."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from inspect import isawaitable
from dataclasses import replace as replace_description
from threading import RLock

from fruitfly_agent.interactive.contracts.commands import CommandDescription, CommandResult, InteractiveCommand
from fruitfly_agent.interactive.terminal.io.completion import CompletionItem, CompletionQuery, CompletionResult

TerminalCommandHandler = Callable[[InteractiveCommand], CommandResult | Awaitable[CommandResult]]


class TerminalCommandRegistry:
    """Handlers receive parsed commands and capture only their own capabilities."""
    def __init__(self, handlers: Mapping[str, TerminalCommandHandler] | None = None) -> None:
        self._lock = RLock()
        self._entries: dict[str, tuple[CommandDescription, TerminalCommandHandler]] = {}
        for name, handler in (handlers or {}).items():
            self.register(name, handler)

    def register(self, name: str, handler: TerminalCommandHandler, *, replace: bool = False,
                 summary: str = '', usage: str = '', discoverable: bool = True) -> None:
        description = CommandDescription(name, summary, usage, discoverable)
        if not callable(handler):
            raise TypeError('terminal command handler must be callable')
        with self._lock:
            if name in self._entries and not replace:
                raise ValueError(f'terminal command already registered: {name}')
            self._entries[name] = description, handler

    def descriptions(self) -> tuple[CommandDescription, ...]:
        with self._lock:
            return tuple(description for description, _ in self._entries.values())

    async def execute(self, command: InteractiveCommand) -> CommandResult | None:
        with self._lock:
            entry = self._entries.get(command.name)
        handler = entry[1] if entry is not None else None
        if handler is None:
            return None
        value = handler(command)
        result = await value if isawaitable(value) else value
        if not isinstance(result, CommandResult):
            raise TypeError("terminal command handler must return CommandResult")
        return result


def effective_commands(base: tuple[CommandDescription, ...], terminal: tuple[CommandDescription, ...]) -> tuple[CommandDescription, ...]:
    """Use the same terminal-first precedence as execution, including hidden overrides."""
    merged = {item.name: item for item in base}
    for item in terminal:
        previous = merged.get(item.name)
        merged[item.name] = replace_description(item, aliases=previous.aliases) if previous is not None else item
    aliases = {alias for item in merged.values() for alias in item.aliases}
    return tuple(sorted((item for item in merged.values() if item.name not in aliases), key=lambda item: item.name))


def complete_command(query: CompletionQuery, descriptions: tuple[CommandDescription, ...]) -> CompletionResult | None:
    """Complete only the leading command token, without filesystem or handler queries."""
    text, cursor = query.text, query.cursor
    if not 0 <= cursor <= len(text) or '\n' in text or '\r' in text:
        return None
    start = len(text) - len(text.lstrip())
    if not text[start:].startswith('/') or cursor <= start:
        return None
    end = start + len(text[start:].split(maxsplit=1)[0])
    if cursor > end or '/' in text[start + 1:end] or '\\' in text[start + 1:end]:
        return None
    prefix = text[start + 1:cursor].lower()
    items = []
    for item in descriptions:
        if not item.discoverable:
            continue
        for name in (item.name, *item.aliases):
            if name.startswith(prefix):
                usage = item.usage or '/' + item.name
                detail = item.summary + (' · ' + usage if usage != '/' + name else '')
                items.append(CompletionItem('/' + name, detail, '/' + name))
    if not items:
        return None
    return CompletionResult(start, end, tuple(sorted(items, key=lambda item: item.label)))
