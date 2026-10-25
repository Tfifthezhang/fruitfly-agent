"""Frontend-neutral command envelopes and handler contracts."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from fruitfly_agent.interactive.contracts.events import InteractiveEvent
from fruitfly_agent.interactive.contracts.models import InteractiveStatus


@dataclass(frozen=True)
class CommandDescription:
    """Read-only discovery metadata; never grants execution authority."""
    name: str
    summary: str = ''
    usage: str = ''
    discoverable: bool = True
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (self.name, *self.aliases):
            if not name or name != name.lower() or any(c.isspace() or c in '/\\' for c in name):
                raise ValueError('command name must be one lowercase path-free token')


def format_command_help(descriptions: tuple[CommandDescription, ...], *, include_hidden: bool = False) -> str:
    rows = ['Commands:']
    for item in sorted(descriptions, key=lambda value: value.name):
        if not item.discoverable and not include_hidden:
            continue
        usage = item.usage or '/' + item.name
        aliases = ' (alias: ' + ', '.join('/' + name for name in item.aliases) + ')' if item.aliases else ''
        rows.append(f'  {usage:<22} {item.summary}{aliases}'.rstrip())
    return '\n'.join(rows) + '\n'


@dataclass(frozen=True)
class InteractiveCommand:
    name: str
    arguments: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandSection:
    """Read-only labelled rows; category is a presentation hint."""
    category: str
    title: str
    rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CommandPanel:
    """Optional structured presentation alongside a command's text fallback."""
    title: str
    sections: tuple[CommandSection, ...]
    footer: str = ""


@dataclass(frozen=True)
class CommandResult:
    text: str = ""
    should_exit: bool = False
    panel: CommandPanel | None = None


class CommandContext(Protocol):
    @property
    def status(self) -> InteractiveStatus: ...

    def trace(self, limit: int = 12) -> list[InteractiveEvent]: ...


CommandHandler = Callable[[InteractiveCommand, CommandContext], CommandResult]


