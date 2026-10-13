"""Select and restore a conversation without knowing runtime storage."""
from pathlib import Path
from fruitfly_agent.interactive.contracts.commands import CommandResult
from fruitfly_agent.interactive.terminal.features.resume.menu import TerminalResumeFrontend


def resume_handler(*, resume, discover, status, busy, menu_scope, input_stream,
                   output_stream, line_editor, write, welcome, show_history):
    async def handle(command):
        if busy():
            return CommandResult(text="finish or /cancel the active run before resuming another session\n")
        if command.arguments:
            path = Path(" ".join(command.arguments))
            if not path.is_absolute():
                path = Path(status().working_directory) / path
            path = path.resolve()
        else:
            if discover is None:
                return CommandResult(text="the /resume session picker is unavailable in this frontend\n")
            try:
                sessions = discover()
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                return CommandResult(text=f"could not list sessions: {exc}\n")
            if not sessions:
                return CommandResult(text="no saved non-empty sessions are available\n")
            with menu_scope():
                selected = TerminalResumeFrontend(
                    sessions, input_stream=input_stream, output_stream=output_stream,
                    line_editor=line_editor(),
                ).run()
            path = Path(selected.path) if selected is not None else None
        if path is None:
            return CommandResult()
        try:
            await resume(path)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return CommandResult(text=f"could not resume session: {exc}\n")
        write(f"\n[resumed {path} using current configuration]\n")
        welcome(status())
        await show_history()
        return CommandResult()
    return handle
