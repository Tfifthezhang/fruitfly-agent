"""Line-oriented rendering of interactive events."""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from collections.abc import Callable
from typing import TextIO

from ..events import (
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
from ..models import InteractiveStatus
from .branding import FRUIT_FLY_ICON
from .live import prompt_frame_lines
from .markdown import MarkdownStreamPresenter, MarkdownUpdate
from .text import colors_enabled, supports_ansi, terminal_columns, truncate_cells
from .welcome import render_welcome


_BLUE = "\033[34m"
_CYAN = "\033[36m"
_DIM = "\033[2m"
_GREEN_BOLD = "\033[1;32m"
_MAGENTA = "\033[35m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_TOOL_ARGUMENT_CELLS = 240
_TOOL_UPDATE_CHARS = 800
_ACTIVITY_INTERVAL_SECONDS = 0.12
_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
_SENSITIVE_ARGUMENT = re.compile(
    r"(?:api[_-]?key|authorization|cookie|password|secret|token)",
    re.IGNORECASE,
)
_ARGUMENT_PRIORITY = {
    "path": 0,
    "command": 1,
    "query": 2,
    "pattern": 3,
    "name": 4,
    "id": 5,
}

_CATEGORY_COLORS = {
    "tools": _CYAN,
    "memory": _MAGENTA,
    "skills": _BLUE,
    "compaction": _YELLOW,
}
_CATEGORY_LABELS = {
    "tools": "tool",
    "memory": "memory",
    "skills": "skill",
}


class TerminalRenderer:
    def __init__(
        self, output: TextIO | None = None, *,
        tool_output_limit: int | None = _TOOL_UPDATE_CHARS,
    ) -> None:
        self._tool_output_limit = tool_output_limit
        self.output = output or sys.stdout
        self._line_open = False
        self._thinking_open = False
        self._terminal_ui = supports_ansi(self.output)
        self._color = colors_enabled(self.output)
        self._markdown = (
            MarkdownStreamPresenter(
                columns=terminal_columns(self.output),
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
        self.output.write(
            render_welcome(
                status,
                columns=terminal_columns(self.output),
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
        top, bottom = prompt_frame_lines(terminal_columns(self.output))
        displayed = text.replace("\n", "\n│ ")
        self.output.write(f"{top}\n❯ {displayed}\n{bottom}\n")
        self.output.flush()

    async def render(self, event: InteractiveEvent) -> None:
        if isinstance(event, RunStarted):
            self._flush_markdown()
            self._set_activity("Preparing")
            return
        if isinstance(event, RunActivityChanged):
            self._set_activity(_format_activity_label(event))
            return
        if isinstance(event, AssistantThinkingDelta):
            self._flush_markdown()
            if not self._thinking_open:
                self._write("thinking> ", _DIM)
                self._thinking_open = True
            self._write(event.text, _DIM)
            self._line_open = True
            return
        if isinstance(event, AssistantTextDelta):
            if self._thinking_open:
                self._newline()
                self._thinking_open = False
            if self._markdown is not None:
                text = event.text
                if not self._assistant_markdown_started:
                    text = text.lstrip("\r\n")
                    if not text:
                        return
                    self._assistant_markdown_started = True
                update = self._markdown.feed(
                    text,
                    columns=terminal_columns(self.output),
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
            self._tool_update_chars = 0
            self._tool_update_truncated = False
            args = _summarize_arguments(event.arguments)
            label = _category_label(event.category)
            self._write(
                f"[{label} {event.tool_name}] ",
                _category_color(event.category),
            )
            self._write(f"{args}\n", _DIM)
            return
        if isinstance(event, ToolOutput):
            if self._tool_update_truncated:
                return
            self._newline()
            remaining = (
                len(event.text) if self._tool_output_limit is None
                else self._tool_output_limit - self._tool_update_chars
            )
            if remaining <= 0:
                self._write("… [live tool output truncated]\n", _DIM)
                self._tool_update_truncated = True
                return
            visible = event.text[:remaining]
            self._tool_update_chars += len(visible)
            self._write(visible, _DIM)
            self._line_open = not visible.endswith("\n")
            if len(event.text) > len(visible):
                self._newline()
                self._write("… [live tool output truncated]\n", _DIM)
                self._tool_update_truncated = True
            return
        if isinstance(event, ToolFinished):
            self._newline()
            suffix = " (terminate)" if event.terminate else ""
            preview = _summarize_result(event.output)
            detail = f" {preview}" if preview else ""
            label = _category_label(event.category)
            self._write(
                f"[{label} {event.tool_name} done]{suffix}",
                _category_color(event.category),
            )
            self._write(f"{detail}\n", _DIM)
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
        update = self._markdown.flush(columns=terminal_columns(self.output))
        self._present_markdown(update)
        if self._assistant_updater is not None and not update.committed:
            self._assistant_updater("", "")
        self._markdown.reset()
        self._assistant_markdown_started = False
        self._assistant_prefix_committed = False

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


def _category_label(category: str) -> str:
    normalized = category.casefold()
    return _CATEGORY_LABELS.get(normalized, normalized.replace("_", "-"))


def _format_activity_label(event: RunActivityChanged) -> str:
    subject = event.subject.strip()
    if event.phase == "waiting_model":
        label = f"Waiting for {subject}" if subject else "Waiting for model"
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


def _summarize_arguments(arguments: dict[str, object]) -> str:
    """Render bounded metadata without dumping source files or secrets."""

    if not arguments:
        return "{}"
    ordered = sorted(
        arguments.items(),
        key=lambda item: (_ARGUMENT_PRIORITY.get(item[0].casefold(), 100), item[0]),
    )
    parts = [f"{key}={_summarize_value(key, value)}" for key, value in ordered]
    return truncate_cells(" · ".join(parts), _TOOL_ARGUMENT_CELLS)


def _summarize_value(key: str, value: object) -> str:
    if _SENSITIVE_ARGUMENT.search(key):
        return "<redacted>"
    if isinstance(value, str):
        lines = value.count("\n") + 1
        if len(value) > 120 or lines > 1:
            return f"<{len(value):,} chars, {lines:,} lines>"
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return f"<{len(value):,} fields>"
    if isinstance(value, (list, tuple)):
        return f"<{len(value):,} items>"
    return json.dumps(value, ensure_ascii=False, default=repr)


def _summarize_result(output: str) -> str:
    stripped = output.strip()
    if not stripped:
        return ""
    lines = stripped.count("\n") + 1
    if len(stripped) > 500 or lines > 3:
        return f"<{len(stripped):,} chars, {lines:,} lines>"
    return truncate_cells(" ".join(stripped.split()), _TOOL_ARGUMENT_CELLS)


__all__ = ["TerminalRenderer"]
