"""Parsing and routing for the built-in interactive command vocabulary."""

from __future__ import annotations

from collections.abc import Mapping
from threading import RLock
from dataclasses import replace as replace_description

from fruitfly_agent.interactive.contracts.commands import (
    CommandDescription,
    format_command_help,
    InteractiveCommand,
    CommandResult,
    CommandPanel,
    CommandSection,
    CommandContext,
    CommandHandler,
)
from fruitfly_agent.interactive.contracts.models import InteractiveMechanism, InteractiveStatus


def parse_command(text: str) -> InteractiveCommand | None:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    parts = stripped[1:].split()
    if not parts:
        return InteractiveCommand(name="")
    name = parts[0].lower()
    # Multi-segment absolute paths are ordinary prompt content, not slash
    # commands. Command names are a single path-free token such as ``/help``.
    if "/" in name or "\\" in name:
        return None
    name = _ALIASES.get(name, name)
    return InteractiveCommand(name=name, arguments=tuple(parts[1:]))


class CommandRouter:
    """Dispatch local commands without coupling them to terminal I/O."""

    def __init__(
        self,
        handlers: Mapping[str, CommandHandler] | None = None,
    ) -> None:
        self._lock = RLock()
        self._entries: dict[str, tuple[CommandDescription, CommandHandler]] = {description.name: (description, self._show_help if handler is None else handler)
                         for description, handler in _BUILTIN_ENTRIES}
        for name, handler in (handlers or {}).items():
            self.register(name, handler, replace=True)

    def register(self, name: str, handler: CommandHandler, *, replace: bool = False,
                 summary: str = '', usage: str = '', discoverable: bool = True) -> None:
        if not callable(handler):
            raise TypeError('command handler must be callable')
        description = CommandDescription(name, summary, usage, discoverable)
        with self._lock:
            if name in self._entries and not replace:
                raise ValueError(f'command already registered: {name}')
            prior = self._entries.get(name)
            if prior is not None:
                description = replace_description(description, aliases=prior[0].aliases)
            self._entries[name] = description, handler

    def descriptions(self) -> tuple[CommandDescription, ...]:
        with self._lock:
            return tuple(description for description, _ in self._entries.values())

    @property
    def uses_default_help(self) -> bool:
        with self._lock:
            return self._entries['help'][1] == self._show_help

    def _show_help(self, command: InteractiveCommand, context: CommandContext) -> CommandResult:
        return CommandResult(text=format_command_help(self.descriptions()))

    def execute(
        self,
        command: InteractiveCommand,
        context: CommandContext,
    ) -> CommandResult:
        with self._lock:
            entry = self._entries.get(command.name)
        handler = entry[1] if entry is not None else None
        if handler is None:
            return CommandResult(
                text=f"unknown command: /{command.name}; use /help\n"
            )
        return handler(command, context)


def _exit(
    command: InteractiveCommand,
    context: CommandContext,
) -> CommandResult:
    return CommandResult(should_exit=True)


def _status(
    command: InteractiveCommand,
    context: CommandContext,
) -> CommandResult:
    status = context.status
    prompt_line = (
        f"base prompt: {status.prompt_label} · {status.prompt_hash[:15]}… (active)\n"
        if status.prompt_label else ""
    )
    list_candidates = getattr(context, "candidates", None)
    pending_candidates: int | str = 0
    if callable(list_candidates):
        try:
            pending_candidates = sum(
                item.status in {"proposed", "reviewed", "deferred"}
                for item in list_candidates()
            )
        except (OSError, TypeError, ValueError):
            pending_candidates = "unavailable"
    return CommandResult(
        text=(
            f"model: {status.model}\n"
            f"{prompt_line}"
            f"{_environment_status(status)}"
            f"session: {status.session_path}\n"
            f"messages: {status.message_count}\n"
            f"state: {status.application_state}\n"
            f"queued: {status.pending_count}\n"
            f"pending candidates: {pending_candidates}\n"
            f"{_context_status(status)}"
        )
    )


def _environment_rows(status: InteractiveStatus) -> tuple[tuple[str, str], ...]:
    environment = status.execution_environment
    rows: tuple[tuple[str, str], ...] = (
        ("Local workspace", status.working_directory),
        ("Execution environment", environment.label if environment is not None else "Unavailable"),
    )
    if environment is not None:
        if environment.server:
            rows += (("Server", environment.server),)
        rows += (("Execution directory", environment.working_directory),)
    return rows


def _environment_status(status: InteractiveStatus) -> str:
    return "".join(f"{label.lower()}: {value}\n" for label, value in _environment_rows(status))


def _context_status(status: InteractiveStatus) -> str:
    tokens = None
    source = ""
    if status.estimated_input_tokens is not None and status.estimate_model == status.model:
        tokens = status.estimated_input_tokens
        source = "estimated; last request"
    elif status.last_input_tokens is not None and status.receipt_model == status.model:
        tokens = status.last_input_tokens
        source = "reported; last request"
    percentage = "unknown"
    if tokens is not None and status.context_window and status.context_window > 0:
        ratio = tokens / status.context_window
        width = 20
        filled = max(0, min(width, int(ratio * width)))
        bar = "#" * filled + "-" * (width - filled)
        percentage = f"[{bar}] {100 * ratio:.1f}% ({source})"
    return (
        f"context usage: {percentage}\n"
        f"compactions: {status.compaction_count:,}\n"
    )


def _lab(
    command: InteractiveCommand,
    context: CommandContext,
) -> CommandResult:
    if command.arguments:
        return CommandResult(text="usage: /lab\n")
    status = context.status
    grouped: dict[str, list[InteractiveMechanism]] = {}
    for mechanism in status.mechanism_details:
        grouped.setdefault(mechanism.category, []).append(mechanism)
    detailed_ids = {
        mechanism.mechanism_id for mechanism in status.mechanism_details
    }
    uncategorized = [
        mechanism_id
        for mechanism_id in status.mechanisms
        if mechanism_id not in detailed_ids
    ]
    if uncategorized:
        grouped.setdefault("other", []).extend(
            InteractiveMechanism(item, "other", item) for item in uncategorized
        )

    if status.tool_names:
        grouped.setdefault("tools", [])
    if status.improvement_available:
        grouped.setdefault("improvement", [])
    grouped.setdefault("environment", [])
    order = {name: index for index, name in enumerate((
        "context-manager", "environment", "tools", "workflow", "improvement",
    ))}
    sections = []
    for category in sorted(grouped, key=lambda name: (order.get(name, len(order)), name)):
        mechanisms = grouped[category]
        if category == "context-manager":
            phases: dict[str, list[str]] = {}
            for item in mechanisms:
                phase = item.display_section or item.context_phase or "other"
                phases.setdefault(phase, []).append(item.label)
            phase_order = ("augmentation", "externalization", "reduction")
            rows = [(_category_label(phase), " · ".join(phases.get(phase, ())) or "Not enabled")
                    for phase in (*phase_order, *sorted(set(phases) - set(phase_order)))]
        elif category == "environment":
            rows = list(_environment_rows(status))
            rows.extend((item.label, "Enabled") for item in mechanisms)
        elif category == "tools":
            rows = []
            described: set[str] = set()
            for item in mechanisms:
                names = [name for name in item.tool_names if name in status.tool_names and name not in described]
                rows.extend((name, item.label) for name in names)
                described.update(names)
                if not item.tool_names:
                    rows.append((item.label, "Enabled"))
            rows.extend((name, "Enabled") for name in dict.fromkeys(status.tool_names) if name not in described)
        else:
            rows = [(item.label, "Enabled") for item in mechanisms]
        if category == "improvement" and status.improvement_available:
            rows.append(("Component workflow", "Available · /improvement"))
        if rows:
            sections.append(CommandSection(category, _category_label(category), tuple(rows)))
    if not sections:
        sections.append(CommandSection("overview", "Overview", (("Mechanisms", "None enabled"),)))
    if status.tool_services:
        rows = []
        for service in status.tool_services:
            rows.extend(((service.name, service.state), ('Transport', service.transport),
                ('Runs on', service.location), ('Working directory', service.working_directory),
                ('Selected remote tools', ', '.join(service.tools))))
        sections.append(CommandSection('tool-services', 'Tool services', tuple(rows)))
    panel = CommandPanel("Lab · Active session", tuple(sections), "Next-session settings: /config")
    text = [panel.title, ""]
    for section in panel.sections:
        text.append(section.title)
        text.extend(f"  {label}: {value}" for label, value in section.rows)
        text.append("")
    text.append(panel.footer)
    return CommandResult(text="\n".join(text) + "\n", panel=panel)


def _category_label(category: str) -> str:
    return category.replace("-", " ").replace("_", " ").title()


def _improvement_unavailable(command: InteractiveCommand, context: CommandContext) -> CommandResult:
    return CommandResult(text="the /improvement menu is unavailable in this embedded frontend\n")


def _trace(
    command: InteractiveCommand,
    context: CommandContext,
) -> CommandResult:
    limit = 12
    if command.arguments:
        try:
            limit = max(1, min(100, int(command.arguments[0])))
        except ValueError:
            return CommandResult(text="usage: /trace [N]\n")
    events = context.trace(limit)
    if not events:
        return CommandResult(text="trace: empty\n")
    rows = []
    for event in events:
        data = event.to_dict()
        rows.append(
            f"{data['sequence']:>3} {data['type']} "
            f"run={str(data['run_id'])[:8]}\n"
        )
    return CommandResult(text="".join(rows))


def _configuration_unavailable(
    command: InteractiveCommand,
    context: CommandContext,
) -> CommandResult:
    return CommandResult(
        text="the /config selection menu is unavailable in this embedded frontend\n"
    )


def _resume_unavailable(
    command: InteractiveCommand,
    context: CommandContext,
) -> CommandResult:
    return CommandResult(
        text="the /resume session picker is unavailable in this embedded frontend\n"
    )


def _permissions(command: InteractiveCommand, context: CommandContext) -> CommandResult:
    if command.arguments != ('clear',):
        return CommandResult(text='usage: /permissions clear\n')
    clear = getattr(context, 'clear_authorizations', None)
    if clear is None:
        return CommandResult(text='authorization service unavailable\n')
    clear()
    return CommandResult(text='temporary approvals cleared\n')

_BUILTIN_ENTRIES: tuple[tuple[CommandDescription, CommandHandler | None], ...] = (
    (CommandDescription('help', 'show this help'), None),
    (CommandDescription('status', 'show model, workspace, session, and context state'), _status),
    (CommandDescription('lab', 'inspect active context, tools, environment, and capabilities'), _lab),
    (CommandDescription('trace', 'show the latest N frontend events (default: 12)', '/trace [N]'), _trace),
    (CommandDescription('permissions', 'revoke temporary approvals', '/permissions clear'), _permissions),
    (CommandDescription('exit', 'leave the interactive session', aliases=('quit',)), _exit),
    (CommandDescription('config', 'requires a configuration frontend', '/config', False), _configuration_unavailable),
    (CommandDescription('resume', 'requires a session picker', '/resume [PATH]', False), _resume_unavailable),
    (CommandDescription('improvement', 'requires an improvement frontend', '/improvement [TEXT]', False), _improvement_unavailable),
)
_ALIASES = {alias: description.name for description, _ in _BUILTIN_ENTRIES for alias in description.aliases}
# Router reference, including frontend placeholders; live help uses effective registrations.
HELP_TEXT = format_command_help(tuple(description for description, _ in _BUILTIN_ENTRIES), include_hidden=True).rstrip()


__all__ = [
    "HELP_TEXT",
    "CommandContext",
    "CommandHandler",
    "CommandResult",
    "CommandRouter",
    "InteractiveCommand",
    "parse_command",
]
