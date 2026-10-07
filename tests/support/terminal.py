"""Finite terminal input and in-memory TTY substitutes."""

import io

from fruitfly_agent.interactive.events import RunFinished


class ScriptedLines:
    def __init__(self, *lines: str | None) -> None:
        self.lines = iter(lines)

    def read_line(self) -> str | None:
        return next(self.lines)


class TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


def run_finished() -> RunFinished:
    return RunFinished(
        run_id="run-1", stop_reason="stop", model="offline-model",
        turn_count=1, tool_call_count=0, input_tokens=1, output_tokens=2,
        is_error=False, error_details=None,
    )
