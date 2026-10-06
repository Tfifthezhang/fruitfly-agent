"""Terminal session picker over renderer-neutral resume candidates."""

from __future__ import annotations

from datetime import datetime
import sys
from typing import TextIO

from ..models import ResumableSession
from .input import LineEditor, create_line_editor
from .menu import (
    MenuAction,
    MenuInput,
    MenuRow,
    TerminalMenuRenderer,
    create_menu_input,
)


class TerminalResumeFrontend:
    """Choose one compatible session without reading storage directly."""

    def __init__(
        self,
        sessions: tuple[ResumableSession, ...],
        *,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
        line_editor: LineEditor | None = None,
        menu_input: MenuInput | None = None,
    ) -> None:
        self.sessions = sessions
        self.input = input_stream or sys.stdin
        self.output = output_stream or sys.stdout
        self.line_editor = line_editor or create_line_editor(self.input, self.output)
        self.menu_input = menu_input or create_menu_input(
            self.input,
            self.output,
            self.line_editor,
        )
        self.renderer = TerminalMenuRenderer(self.output)

    def run(self) -> ResumableSession | None:
        selected = 0
        rows = tuple(self._row(item) for item in self.sessions) + (
            MenuRow("Back", "Keep using the current session"),
        )
        while True:
            self.renderer.render(
                title="FruitFlyAgent · resume",
                subtitle=(
                    "Choose a compatible persisted session. Sessions are switched, "
                    "not merged."
                ),
                rows=rows,
                selected=selected,
                instructions=(
                    "↑↓ move · Enter resume · Esc back · q close menu"
                    if self.renderer.ansi
                    else (
                        "Enter an option number; blank selects highlighted; "
                        "q closes the menu"
                    )
                ),
            )
            event = self.menu_input.read_event()
            if event.index is not None and 0 <= event.index < len(rows):
                selected = event.index
            elif event.action == MenuAction.UP:
                selected = (selected - 1) % len(rows)
                continue
            elif event.action == MenuAction.DOWN:
                selected = (selected + 1) % len(rows)
                continue
            if event.action in {MenuAction.BACK, MenuAction.QUIT}:
                return None
            if event.action != MenuAction.ACTIVATE:
                continue
            if selected == len(self.sessions):
                return None
            return self.sessions[selected]

    @staticmethod
    def _row(session: ResumableSession) -> MenuRow:
        timestamp = datetime.fromtimestamp(session.modified_at).astimezone()
        label = (
            f"{timestamp:%Y-%m-%d %H:%M:%S} · "
            f"{session.message_count} messages"
        )
        runtime = " · ".join(
            value for value in (session.profile, session.model, f"{session.prompt_label} {session.prompt_hash[:15]}…" if session.prompt_label else "") if value
        )
        detail = f"{runtime} · {session.path}" if runtime else session.path
        return MenuRow(label, detail)


__all__ = ["TerminalResumeFrontend"]
