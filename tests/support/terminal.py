"""Finite terminal input and in-memory TTY substitutes."""

import io
import re

from fruitfly_agent.interactive.contracts.events import RunFinished


class ScriptedLines:
    def __init__(self, *lines: str | None) -> None:
        self.lines = iter(lines)

    def read_line(self) -> str | None:
        return next(self.lines)


class TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


def menu_choice(label: str, text: str) -> str:
    """Resolve a visible numbered row, keeping scripts independent of expanded size."""
    plain = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text)
    matches = []
    for line in plain.splitlines():
        match = re.match(r'^\s*>?\s*(\d+)\.\s*(.*)$', line)
        if match:
            name = re.sub(r'^(?:\[[^]]*\]|[✓●○])\s*', '', match[2]).strip()
            if name.startswith(label):
                matches.append(match[1])
    if len(matches) != 1:
        raise AssertionError(f'Expected one visible menu row {label!r}, found {matches!r}: {plain}')
    return matches[0]


class MenuScriptedLines(ScriptedLines):
    """Use @label for a visible row and plain text for chat or field input."""
    def __init__(self, output, *lines):
        super().__init__(*lines)
        self.output, self.offset = output, 0

    def read_line(self):
        line = super().read_line()
        rendered = self.output.getvalue()[self.offset:]
        self.offset = len(self.output.getvalue())
        return menu_choice(line[1:], rendered) if line is not None and line.startswith('@') else line


def run_finished() -> RunFinished:
    return RunFinished(
        run_id="run-1", stop_reason="stop", model="offline-model",
        turn_count=1, tool_call_count=0, input_tokens=1, output_tokens=2,
        is_error=False, error_details=None,
    )


class TerminalSessionStub:
    running = False
    pending_count = 0

    def __init__(self, **kwargs):
        from tests.support.application import offline_session
        self.base = offline_session(**kwargs)

    @property
    def status(self):
        return self.base.status

    def set_event_sink(self, sink):
        self.sink = sink
        self.base.set_event_sink(sink)

    def trace(self, limit=12):
        return self.base.trace(limit)
