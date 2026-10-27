"""Line-oriented rendering of interactive events."""

from __future__ import annotations

import asyncio
import sys
import time
from collections.abc import Callable
from typing import TextIO

from fruitfly_agent.interactive.contracts.events import (
    AuthorizationRequested,
    AuthorizationResolved,
    AssistantTextDelta,
    AssistantThinkingDelta,
    CompactionStarted,
    InteractiveEvent,
    RunActivityChanged,
    RunFinished,
    RunStarted,
    ToolFinished,
    ToolOutput,
    ToolStarted,
)
from fruitfly_agent.interactive.contracts.models import ConversationMessage, InteractiveStatus
from fruitfly_agent.interactive.contracts.commands import CommandResult
from fruitfly_agent.interactive.terminal.rendering.history import render_history_message
from fruitfly_agent.interactive.terminal.rendering.branding import FRUIT_FLY_ICON
from fruitfly_agent.interactive.terminal.rendering.markdown import MarkdownStreamPresenter, MarkdownUpdate, TerminalMarkdownRenderer
from fruitfly_agent.interactive.terminal.io.text import (
    safe_terminal_text,
    colors_enabled,
    input_styles,
    supports_ansi,
    content_columns,
    truncate_cells,
)
from fruitfly_agent.interactive.terminal.rendering.welcome import render_welcome
from fruitfly_agent.interactive.terminal.rendering.tools import summarize_arguments, summarize_result
from fruitfly_agent.interactive.terminal.rendering.panels import render_command_panel


_BLUE = "\033[34m"
_CYAN = "\033[36m"
_DIM = "\033[2m"
_GREEN_BOLD = "\033[1;32m"
_MAGENTA = "\033[35m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_TOOL_UPDATE_CHARS = 800
_ACTIVITY_INTERVAL_SECONDS = 0.12
_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

_CATEGORY_COLORS = {
    "tools": _CYAN,
    "memory": _MAGENTA,
    "skills": _BLUE,
    "compaction": _YELLOW,
}
def _tool_description(description: str, name: str, columns: int) -> str:
    return truncate_cells(' '.join(safe_terminal_text(description or name).split()), max(8, columns - 4))


class TerminalRenderer:
    def __init__(
        self, output: TextIO | None = None, *,
        tool_output_limit: int | None = _TOOL_UPDATE_CHARS,
    ) -> None:
        self._tool_output_limit = tool_output_limit
        self.output = output or sys.stdout
        self._line_open = False
        self._terminal_ui = supports_ansi(self.output)
        self._color = colors_enabled(self.output)
        self._markdown = (
            MarkdownStreamPresenter(
                columns=content_columns(self.output),
                color=self._color,
            )
            if self._terminal_ui
            else None
        )
        assistant_updater = getattr(self.output, "update_assistant", None)
        self._assistant_updater: Callable[[str, str], None] | None = (
            assistant_updater
            if self._terminal_ui and callable(assistant_updater)
            else None
        )
        self._assistant_markdown_started = False
        formatted = getattr(self.output, 'formatted_output', None)
        self._formatted: Callable[..., None] | None = (
            formatted if self._terminal_ui and callable(formatted) else None
        )
        self._source = ''
        self._source_updated_at = 0.0
        self._assistant_prefix_committed = False
        self._tool_update_chars = 0
        self._tool_update_truncated = False
        setter = getattr(self.output, "set_activity", None)
        self._activity_setter: Callable[[str], None] | None = (
            setter if self._terminal_ui and callable(setter) else None
        )
        self._activity_label = ""
        self._activity_started_at = 0.0
        self._activity_frame = 0
        self._activity_task: asyncio.Task[None] | None = None

    def show_welcome(self, status: InteractiveStatus) -> None:
        self._flush_markdown()
        self.finish_line()
        if self._formatted is not None:
            self._formatted('', lambda source, columns: render_welcome(
                status, columns=columns, terminal_ui=True, color=self._color,
            ), complete=True)
            return
        self.output.write(
            render_welcome(
                status,
                columns=content_columns(self.output),
                terminal_ui=self._terminal_ui,
                color=self._color,
            )
        )
        self.output.flush()

    def write_system(self, text: str) -> None:
        self._flush_markdown()
        self.finish_line()
        self.output.write(text)
        self.output.flush()

    def write_command_result(self, result: CommandResult) -> None:
        if result.panel is not None:
            if self._formatted is not None:
                self.finish_line()
                self._formatted('', lambda source, columns: render_command_panel(
                    result.panel, columns=columns, color=self._color,
                ), complete=True)
                return
            self.write_system(render_command_panel(
                result.panel, columns=content_columns(self.output), color=self._color,
            ))
        elif result.text:
            self.write_system(result.text)

    async def show_history(self, messages: tuple[ConversationMessage, ...]) -> None:
        """Append saved conversation once, without emitting live run events."""
        if not messages:
            return
        self._flush_markdown()
        await self._stop_activity()
        self.finish_line()
        self.write_system("\n[Restored conversation]\n\n")
        for message in messages:
            if self._formatted is not None:
                def format_history(source: str, columns: int, item: ConversationMessage = message) -> str:
                    return render_history_message(item, columns=columns, terminal_ui=True, color=self._color)
                self._formatted('', format_history, complete=True)
            else:
                self.output.write(render_history_message(
                    message, columns=content_columns(self.output),
                    terminal_ui=self._terminal_ui, color=self._color,
                ))
            self.output.flush()
            await asyncio.sleep(0)
        self.write_system("[End of restored conversation]\n\n")

    def write_log(self, text: str) -> None:
        """Append a raw log fragment without inserting newlines between chunks."""

        self._flush_markdown()
        self.output.write(text)
        if text:
            self._line_open = not text.endswith("\n")
        self.output.flush()

    def write_user_input(self, text: str) -> None:
        """Copy a fixed-editor submission into the scrolling transcript."""

        self.finish_line()
        _, accent = input_styles(self.output)
        reset = "\x1b[0m" if accent else ""
        lines = text.split("\n")
        self.output.write("\n")
        for index, line in enumerate(lines):
            prefix = "❯ " if index == 0 else "│ "
            self.output.write(f"{accent}{prefix}{reset}{line}\n")
        self.output.write("\n")
        self.output.flush()

    async def render(self, event: InteractiveEvent) -> None:
        if isinstance(event, AuthorizationRequested):
            self.write_system("\nPermission required: " + safe_terminal_text(event.tool_name) + " / " + event.operation + "\n")
            for target in event.targets:
                self.write_system("target: " + safe_terminal_text(target) + "\n")
            self.write_system(safe_terminal_text(event.summary) + "\n")
            if event.operation == "execute":
                self.write_system("Local code runs with current user permissions; file/network isolation is unavailable.\n")
            if not callable(getattr(self.output, "set_choices", None)):
                self.write_system("1. Allow once (Enter)\n2. " + safe_terminal_text(event.session_label) + "\n3. Deny (Esc)\n")
            return
        if isinstance(event, AuthorizationResolved):
            self.write_system("permission: " + event.choice + "\n")
            return
        if isinstance(event, RunStarted):
            self._flush_markdown()
            self._tool_update_chars = 0
            self._tool_update_truncated = False
            self._set_activity("Preparing")
            return
        if isinstance(event, RunActivityChanged):
            self._set_activity(_format_activity_label(event))
            return
        if isinstance(event, AssistantThinkingDelta):
            # RunActivityChanged carries progress; reasoning never enters the transcript.
            return
        if isinstance(event, AssistantTextDelta):
            if self._markdown is not None:
                text = event.text
                if not self._assistant_markdown_started:
                    text = text.lstrip("\r\n")
                    if not text:
                        return
                    self._assistant_markdown_started = True
                if self._formatted is not None:
                    self._source += text
                    now = time.monotonic()
                    if now - self._source_updated_at >= 0.05:
                        self._formatted(self._source, self._format_answer)
                        self._source_updated_at = now
                    return
                update = self._markdown.feed(
                    text,
                    columns=content_columns(self.output),
                )
                self._present_markdown(update)
                return
            if not self._line_open:
                text = event.text.lstrip("\r\n")
                if not text:
                    return
                self._write(f"{FRUIT_FLY_ICON} ", _GREEN_BOLD)
            else:
                text = event.text
            self._write(text)
            self._line_open = True
            return
        if isinstance(event, ToolStarted):
            self._flush_markdown()
            self._newline()
            args = summarize_arguments(event.arguments)
            description = _tool_description(event.description, event.tool_name, content_columns(self.output))
            self._write(
                f"◐ {description}\n",
                _category_color(event.category),
            )
            self._write(f"  {safe_terminal_text(event.tool_name)} · {args}\n", _DIM)
            return
        if isinstance(event, ToolOutput):
            if self._tool_update_truncated:
                return
            self._newline()
            text = safe_terminal_text(event.text)
            remaining = (
                len(text) if self._tool_output_limit is None
                else self._tool_output_limit - self._tool_update_chars
            )
            if remaining <= 0:
                self._write("… [live tool output truncated]\n", _DIM)
                self._tool_update_truncated = True
                return
            visible = text[:remaining]
            self._tool_update_chars += len(visible)
            self._write(visible, _DIM)
            self._line_open = not visible.endswith("\n")
            if len(text) > len(visible):
                self._newline()
                self._write("… [live tool output truncated]\n", _DIM)
                self._tool_update_truncated = True
            return
        if isinstance(event, ToolFinished):
            self._newline()
            suffix = " · requested stop" if event.terminate else ""
            preview = (summarize_result(event.output) if event.status not in {'failed', 'cancelled'} else
                       truncate_cells(' '.join(safe_terminal_text(event.output).split()), 240))
            marker, status, color = {
                'succeeded': ('✓', 'Completed', _GREEN_BOLD),
                'failed': ('✗', 'Failed', _RED),
                'cancelled': ('○', 'Cancelled', _YELLOW),
            }.get(event.status, ('·', 'Finished', _category_color(event.category)))
            description = _tool_description(event.description, event.tool_name,
                content_columns(self.output) - len(status) - len(suffix) - 3)
            self._write(
                f"{marker} {description} · {status}{suffix}\n", color,
            )
            elapsed = f' · {event.elapsed_seconds:.1f}s' if event.elapsed_seconds is not None else ''
            self._write(f"  {preview}{elapsed}\n", _DIM)
            return
        if isinstance(event, CompactionStarted):
            self._newline()
            self._write(
                f"[compaction {event.mechanism_id or 'unknown'} via {event.trigger}; "
                f"{event.estimated_tokens} estimated tokens]\n",
                _YELLOW,
            )
            return
        if isinstance(event, RunFinished):
            self._flush_markdown()
            await self._stop_activity()
            self._newline()
            if event.stop_reason == "aborted":
                self._write("[run cancelled; completed effects are retained]\n", _YELLOW)
            if event.is_error:
                self._write(f"[run failed] {event.error_details}\n", _RED)
            self._write(
                f"[{event.model} | {event.turn_count} turns | "
                f"{event.tool_call_count} tool calls | {event.input_tokens} in / "
                f"{event.output_tokens} out]\n",
                _DIM,
            )

    async def close(self) -> None:
        """Stop presentation-only background work and clear the live status."""

        self._flush_markdown()
        await self._stop_activity()

    def finish_line(self) -> None:
        self._flush_markdown()
        self._newline()

    def _present_markdown(self, update: MarkdownUpdate) -> None:
        if not update.committed and not update.preview_changed:
            return
        committed = update.committed
        preview = update.preview
        prefix = self._assistant_prefix()
        if committed and not self._assistant_prefix_committed:
            committed = prefix + committed
            self._assistant_prefix_committed = True
        elif preview and not self._assistant_prefix_committed:
            preview = prefix + preview

        if self._assistant_updater is not None:
            self._assistant_updater(committed, preview)
            return
        if committed:
            self.output.write(committed)
            self.output.flush()

    def _flush_markdown(self) -> None:
        if self._markdown is None or not self._assistant_markdown_started:
            return
        if self._formatted is not None:
            self._formatted(self._source, self._format_answer, complete=True)
            self._source = ''
            self._assistant_markdown_started = False
            self._source_updated_at = 0.0
            return
        update = self._markdown.flush(columns=content_columns(self.output))
        self._present_markdown(update)
        if self._assistant_updater is not None and not update.committed:
            self._assistant_updater("", "")
        self._markdown.reset()
        self._assistant_markdown_started = False
        self._assistant_prefix_committed = False

    def _format_answer(self, source: str, columns: int) -> str:
        return self._assistant_prefix() + '\n' + TerminalMarkdownRenderer(
            columns=columns, color=self._color,
        ).render(source)

    def _assistant_prefix(self) -> str:
        text = f"{FRUIT_FLY_ICON} "
        if self._color:
            return f"{_GREEN_BOLD}{text}\033[0m"
        return text

    def _newline(self) -> None:
        if self._line_open:
            self.output.write("\n")
            self.output.flush()
            self._line_open = False

    def _write(self, text: str, color: str = "") -> None:
        if self._color and color:
            self.output.write(f"{color}{text}\033[0m")
        else:
            self.output.write(text)
        self.output.flush()

    def _set_activity(self, label: str) -> None:
        label = label.strip()
        if not label or label == self._activity_label:
            return
        self._activity_label = label
        self._activity_started_at = time.monotonic()
        self._activity_frame = 0
        if self._activity_setter is None:
            self._newline()
            self._write(f"[activity] {label}\n", _DIM)
            return
        self._render_activity()
        if self._activity_task is None or self._activity_task.done():
            self._activity_task = asyncio.create_task(self._animate_activity())

    def _render_activity(self) -> None:
        if self._activity_setter is None or not self._activity_label:
            return
        elapsed = max(0.0, time.monotonic() - self._activity_started_at)
        frame = _SPINNER_FRAMES[self._activity_frame % len(_SPINNER_FRAMES)]
        self._activity_setter(
            f"{frame} {self._activity_label} · {elapsed:.1f}s"
        )

    async def _animate_activity(self) -> None:
        try:
            while self._activity_label:
                await asyncio.sleep(_ACTIVITY_INTERVAL_SECONDS)
                self._activity_frame += 1
                self._render_activity()
        except asyncio.CancelledError:
            return
        except Exception:
            # Animation is presentation-only and must not affect an Agent run.
            return

    async def _stop_activity(self) -> None:
        task, self._activity_task = self._activity_task, None
        self._activity_label = ""
        if self._activity_setter is not None:
            self._activity_setter("")
        if task is None or task is asyncio.current_task():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def _category_color(category: str) -> str:
    return _CATEGORY_COLORS.get(category.casefold(), _CYAN)


def _format_activity_label(event: RunActivityChanged) -> str:
    subject = event.subject.strip()
    if event.phase == "waiting_model":
        label = f"Waiting for {subject}" if subject else "Waiting for model"
        if event.attempt:
            label += f" · attempt {event.attempt}/{event.max_attempts}"
        label += " · /cancel or Ctrl+C to stop"
    elif event.phase == "provider_retrying":
        status = f"HTTP {event.status_code}" if event.status_code is not None else event.error_kind
        label = f"Retrying after {status}; attempt {event.attempt + 1}/{event.max_attempts} in {event.delay_seconds:.1f}s"
    elif event.phase == "provider_timeout":
        label = f"Provider waiting deadline exceeded ({event.error_kind})"
    elif event.phase == 'server_tool':
        label = f'Provider tool {subject}'
    elif event.phase == "receiving_thinking":
        label = "Receiving model reasoning"
    elif event.phase == "receiving_answer":
        label = "Receiving answer"
    elif event.phase == "running_tool":
        label = f"Running {subject}" if subject else "Running tool"
    elif event.phase == "processing_tool_result":
        label = (
            f"Processing {subject} result"
            if subject
            else "Processing tool result"
        )
    elif event.phase == "compacting":
        label = "Compacting context"
    elif event.phase == "finalizing":
        label = "Finalizing"
    else:
        label = event.phase.replace("_", " ").strip().capitalize() or "Working"
    if event.request_index > 0:
        label += f" · request {event.request_index}"
    return label




__all__ = ["TerminalRenderer"]
