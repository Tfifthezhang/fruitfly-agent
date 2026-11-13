"""Select and restore a conversation without knowing runtime storage."""
import asyncio
from queue import Queue, Empty
from threading import Thread, Event
from pathlib import Path
from fruitfly_agent.interactive.contracts.commands import CommandResult
from fruitfly_agent.interactive.terminal.features.resume.menu import TerminalResumeFrontend


def history_handler(show_history):
    async def handle(command):
        if command.arguments not in ((), ('older',)):
            return CommandResult(text='usage: /history [older]\n')
        await show_history(older=bool(command.arguments))
        return CommandResult()
    return handle


def resume_handler(*, resume, discover, status, busy, menu_scope, input_stream,
                   output_stream, line_editor, write, welcome, show_history, discover_progress=None):
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
                if discover_progress is not None:
                    updates, cancelled, done = Queue(maxsize=1), Event(), Event()
                    failure = []
                    def publish(sessions):
                        if cancelled.is_set():
                            raise InterruptedError('session discovery cancelled')
                        try:
                            updates.get_nowait()
                        except Empty:
                            pass
                        updates.put_nowait(sessions)
                    def scan():
                        try:
                            publish(discover_progress(publish))
                        except (OSError, RuntimeError, TypeError, ValueError) as exc:
                            if not cancelled.is_set():
                                failure.append(str(exc))
                        finally:
                            done.set()
                    worker = Thread(target=scan, name='session-discovery', daemon=True)
                    worker.start()
                    def poll_updates():
                        try:
                            sessions = updates.get_nowait()
                        except Empty:
                            sessions = None
                        return sessions, not done.is_set(), failure[0] if failure else ''
                    try:
                        with menu_scope():
                            selected = TerminalResumeFrontend((), input_stream=input_stream,
                                output_stream=output_stream, line_editor=line_editor()).run(updates=poll_updates)
                    finally:
                        cancelled.set()
                    path = Path(selected.path) if selected is not None else None
                else:
                    sessions = await asyncio.to_thread(discover)
                    if not sessions:
                        return CommandResult(text="no saved non-empty sessions are available\n")
                    with menu_scope():
                        selected = TerminalResumeFrontend(
                            sessions, input_stream=input_stream, output_stream=output_stream,
                            line_editor=line_editor(),
                        ).run()
                    path = Path(selected.path) if selected is not None else None
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                return CommandResult(text=f"could not list sessions: {exc}\n")
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
