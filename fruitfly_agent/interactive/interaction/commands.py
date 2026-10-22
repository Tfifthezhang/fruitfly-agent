"""Parsing and routing for the built-in interactive command vocabulary."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from fruitfly_agent.interactive.contracts.commands import (
    InteractiveCommand,
    CommandResult,
    CommandPanel,
    CommandSection,
    CommandContext,
    CommandHandler,
)
from fruitfly_agent.interactive.contracts.models import InteractiveMechanism, InteractiveStatus


HELP_TEXT = """Commands:
  /help          show this help
  /status        show model, workspace, session, and context state
  /lab           inspect active context, tools, environment, and capabilities
  /config        open the model and mechanism selection menu
  /improvement [TEXT]  choose an H/S/I target, run improvement, or review candidates
  /resume [PATH] continue saved history using current configuration
  /cancel        cooperatively stop the active run
  /permissions clear  revoke temporary approvals\n  /trace [N]     show the latest N frontend events (default: 12)
  /exit          leave the interactive session"""


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
    if name == "quit":
        name = "exit"
    return InteractiveCommand(name=name, arguments=tuple(parts[1:]))


class CommandRouter:
    """Dispatch local commands without coupling them to terminal I/O."""

    def __init__(
        self,
        handlers: Mapping[str, CommandHandler] | None = None,
    ) -> None:
        self._handlers = dict(_BUILTIN_HANDLERS)
        self._handlers["config"] = _configuration_unavailable
        self._handlers["resume"] = _resume_unavailable
        self._handlers["improvement"] = _improvement_unavailable
        if handlers is not None:
            self._handlers.update(handlers)

    def execute(
        self,
        command: InteractiveCommand,
        context: CommandContext,
    ) -> CommandResult:
        handler = self._handlers.get(command.name)
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


def _help(
    command: InteractiveCommand,
    context: CommandContext,
) -> CommandResult:
    return CommandResult(text=HELP_TEXT + "\n")


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
            f"cwd: {status.working_directory}\n"
            f"session: {status.session_path}\n"
            f"messages: {status.message_count}\n"
            f"state: {status.application_state}\n"
            f"queued: {status.pending_count}\n"
            f"pending candidates: {pending_candidates}\n"
            f"{_context_status(status)}"
        )
    )


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


def _permissions(command, context):
    if command.arguments != ('clear',):
        return CommandResult(text='usage: /permissions clear\n')
    clear = getattr(context, 'clear_authorizations', None)
    if clear is None:
        return CommandResult(text='authorization service unavailable\n')
    clear()
    return CommandResult(text='temporary approvals cleared\n')

_BUILTIN_HANDLERS: dict[str, CommandHandler] = {
    "permissions": _permissions,
    "exit": _exit,
    "help": _help,
    "status": _status,
    "lab": _lab,
    "trace": _trace,
}


__all__ = [
    "HELP_TEXT",
    "CommandContext",
    "CommandHandler",
    "CommandResult",
    "CommandRouter",
    "InteractiveCommand",
    "parse_command",
]
