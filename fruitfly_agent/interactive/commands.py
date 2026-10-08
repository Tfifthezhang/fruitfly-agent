"""Parsing and routing for the built-in interactive command vocabulary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .events import InteractiveEvent
from .models import InteractiveMechanism, InteractiveStatus


HELP_TEXT = """Commands:
  /help          show this help
  /status        show model, workspace, session, and context state
  /lab           show active experimental mechanisms by category
  /config        open the model and mechanism selection menu
  /optimize [TEXT]  open optimization, review candidates, or start a search
  /eval          test the current setup or compare one mechanism
  /resume [PATH] switch to a compatible persisted session
  /cancel        cooperatively stop the active run
  /permissions clear  revoke temporary approvals\n  /trace [N]     show the latest N frontend events (default: 12)
  /exit          leave the interactive session"""


@dataclass(frozen=True)
class InteractiveCommand:
    name: str
    arguments: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandResult:
    text: str = ""
    should_exit: bool = False


class CommandContext(Protocol):
    @property
    def status(self) -> InteractiveStatus: ...

    def trace(self, limit: int = 12) -> list[InteractiveEvent]: ...


CommandHandler = Callable[[InteractiveCommand, CommandContext], CommandResult]


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
        self._handlers["eval"] = _evaluation_unavailable
        self._handlers["resume"] = _resume_unavailable
        self._handlers["optimize"] = _optimization_unavailable
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
        percentage = f"{100 * tokens / status.context_window:.1f}% ({source})"
    return (
        f"context usage: {percentage}\n"
        f"compactions: {status.compaction_count:,}\n"
    )


def _lab(
    command: InteractiveCommand,
    context: CommandContext,
) -> CommandResult:
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

    rows = ["Lab mechanisms\n"]
    if grouped:
        for category in sorted(grouped):
            rows.append(f"  {_category_label(category)}\n")
            mechanisms = grouped[category]
            if category == "context-manager":
                for phase in (
                    "augmentation",
                    "externalization",
                    "reduction",
                ):
                    labels = [
                        item.label
                        for item in mechanisms
                        if item.display_section == phase
                    ]
                    rows.append(f"    {_category_label(phase)}\n")
                    rows.extend(f"      - {label}\n" for label in labels)
                    if not labels:
                        rows.append("      - none\n")
            else:
                rows.extend(f"    - {item.label}\n" for item in mechanisms)
    else:
        rows.append("  none\n")
    return CommandResult(text="".join(rows))


def _category_label(category: str) -> str:
    return category.replace("-", " ").replace("_", " ").title()


def _optimization_unavailable(command: InteractiveCommand, context: CommandContext) -> CommandResult:
    return CommandResult(text="optimization commands require the interactive application\n")


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


def _evaluation_unavailable(
    command: InteractiveCommand,
    context: CommandContext,
) -> CommandResult:
    return CommandResult(
        text="the /eval selection menu is unavailable in this embedded frontend\n"
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
