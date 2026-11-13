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
    help_group: str = 'commands'

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




def command_help_result(descriptions: tuple[CommandDescription, ...], arguments: tuple[str, ...] = ()) -> CommandResult:
    """Use effective declarations for both compact discovery and detailed help."""
    if len(arguments) > 1:
        return CommandResult(text='usage: /help [COMMAND|all]\n')
    requested = arguments[0].lstrip('/') if arguments else ''
    visible = tuple(item for item in descriptions if item.discoverable)
    if requested and requested != 'all':
        item = next((item for item in visible if requested in (item.name, *item.aliases)), None)
        if item is None:
            return CommandResult(text=f'unknown command: /{requested}; use /help\n')
        text = format_command_help((item,))
        return CommandResult(text=text, panel=CommandPanel('/' + item.name, (
            CommandSection('commands', 'Usage', ((item.usage or '/' + item.name, item.summary),)),),
            'Aliases: ' + ', '.join('/' + name for name in item.aliases) if item.aliases else ''))
    selected = tuple(item for item in visible if requested == 'all' or item.help_group != 'diagnostics')
    groups = sorted({item.help_group for item in selected})
    sections = tuple(CommandSection(group, group.replace('-', ' ').title(), tuple(
        ('/' + item.name, item.summary) for item in sorted(selected, key=lambda item: item.name)
        if item.help_group == group)) for group in groups)
    return CommandResult(text=format_command_help(selected), panel=CommandPanel('Commands:', sections,
        '/help COMMAND for arguments · /help all for diagnostics'))
