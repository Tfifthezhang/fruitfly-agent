"""Input loop for the built-in line-oriented terminal adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import signal
import time
import threading
from typing import Protocol, TextIO

from ..models import InteractiveStatus
from ..events import AuthorizationRequested, AuthorizationResolved
from ..optimization import OptimizationClient, format_optimization_activity
from ..dispatch import EventSink

from ..configuration import ConfigurationController
from ..evaluation import EvaluationController
from ..commands import CommandRouter, parse_command
from .configuration import TerminalConfigurationFrontend
from .evaluation import TerminalEvaluationFrontend
from .input import LineEditor, create_line_editor, PollingLineEditor
from .live import InlineTerminalDisplay, create_inline_terminal, InputInterrupted
from .renderer import TerminalRenderer
from .resume import TerminalResumeFrontend
from .screen import transient_screen
from .optimization import TerminalOptimizationFrontend
from .text import safe_terminal_text


class TerminalSession(Protocol):
    @property
    def status(self) -> InteractiveStatus: ...
    @property
    def running(self) -> bool: ...
    def set_event_sink(self, sink: EventSink | None) -> None: ...
    def steer(self, prompt: str) -> bool: ...
    def cancel(self) -> bool: ...
    async def submit(self, prompt: str): ...


class TerminalFrontend:
    """Route terminal input while delegating state and rendering."""

    def __init__(
        self,
        session: TerminalSession,
        *,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
        renderer: TerminalRenderer | None = None,
        line_editor: LineEditor | None = None,
        command_router: CommandRouter | None = None,
        configuration: ConfigurationController | None = None,
        evaluation: EvaluationController | None = None,
    ) -> None:
        self.session = session
        self._last_optimization_notice = 0
        self._last_interrupt = 0.0
        self._interrupt_exit = False
        self._reader_interrupt = threading.Event()
        self._signal_installed = False
        self._previous_sigint = None
        self._last_optimization_activity = None
        self.input = input_stream or sys.stdin
        self.output = output_stream or sys.stdout
        self._inline_display: InlineTerminalDisplay | None = None
        if renderer is None and line_editor is None:
            isolated = create_inline_terminal(self.input, self.output)
            if isolated is not None:
                self._inline_display, line_editor = isolated
                renderer = TerminalRenderer(self._inline_display)
        self.renderer = renderer or TerminalRenderer(self.output)
        self.line_editor = line_editor or create_line_editor(self.input, self.output)
        if command_router is not None and configuration is not None:
            raise ValueError("pass command_router or configuration, not both")
        self.configuration = configuration or getattr(session, "configuration", None)
        self.menu_input = None
        self.menu_renderer = None
        if isinstance(session, OptimizationClient):
            from .menu import create_menu_input, TerminalMenuRenderer
            self.menu_input = create_menu_input(self.input, self.output, self.line_editor)
            self.menu_renderer = TerminalMenuRenderer(self.output)
        self.evaluation = evaluation
        self.command_router = command_router or CommandRouter()
        self._reading_authorization = False
        self.session.set_event_sink(self._render_event)

    async def run(self) -> int:
        try:
            self._activate_inline_terminal()
            if self.input is sys.stdin and self.input.isatty():
                self._previous_sigint = signal.getsignal(signal.SIGINT)
                asyncio.get_running_loop().add_signal_handler(signal.SIGINT, self._signal_interrupt)
                self._signal_installed = True
                if self._inline_display is None:
                    self.line_editor = PollingLineEditor(self.input, self.output, self._reader_interrupt)
            enable = getattr(self.session, "enable_authorization", None)
            if enable is not None:
                enable(bool(self.input.isatty()))
            self.renderer.show_welcome(self.session.status)
            await self._show_history()
            self._show_candidate_notice()
            return await self._run_loop()
        finally:
            enable = getattr(self.session, "enable_authorization", None)
            if enable is not None:
                enable(False)
            self._reader_interrupt.set()
            interrupt = getattr(self.line_editor, "interrupt", None)
            if interrupt is not None:
                interrupt()
            if self._signal_installed:
                asyncio.get_running_loop().remove_signal_handler(signal.SIGINT)
                signal.signal(signal.SIGINT, self._previous_sigint)
                self._signal_installed = False
            try:
                await self.renderer.close()
            finally:
                try:
                    self.renderer.finish_line()
                finally:
                    self._suspend_inline_terminal()

    async def _run_loop(self) -> int:
        while True:
            await asyncio.sleep(0)
            self._show_optimization_activity()
            self._show_optimization_notice()
            self._show_candidate_notice()
            if self._interrupt_exit:
                return 0
            try:
                line = await self._read_prompt_line()
            except InputInterrupted as exc:
                # Signal handlers already performed the action on the loop.
                if exc.handled:
                    self._reader_interrupt.clear()
                elif self._handle_interrupt():
                    return 0
                continue
            if line is None:
                self.renderer.finish_line()
                wait = getattr(self.session, "wait_until_idle", None)
                if wait is not None:
                    await wait()
                return 0
            if self._authorization_pending() is not None:
                self._answer_authorization(line)
                continue
            self._last_interrupt = 0.0
            submitted = line.rstrip("\r\n")
            text = submitted.strip()
            if not text:
                continue
            if self._inline_display is not None:
                self.renderer.write_user_input(submitted)
            command = parse_command(text)
            if command is None:
                if bool(getattr(self.session, "running", False)) and self.session.steer(text):
                    self.renderer.write_system("message added to current run\n")
                    continue
                enqueue = getattr(self.session, "enqueue", None)
                if enqueue is None:
                    task = asyncio.create_task(self.session.submit(text))
                    self.renderer.write_system("running; Ctrl+C cancels in an interactive terminal\n")
                    await task
                else:
                    was_running = bool(getattr(self.session, "running", False))
                    try:
                        position = enqueue(text)
                    except (RuntimeError, ValueError) as exc:
                        self.renderer.write_system(f"cannot submit: {exc}\n")
                        continue
                    if was_running or position > 1:
                        self.renderer.write_system(
                            f"queued prompt ({position} pending)\n"
                        )
                    wait = getattr(self.session, "wait_until_idle", None)
                    if wait is not None and self._inline_display is None:
                        # A readline frame and streamed model output cannot safely
                        # own the same cursor in the fallback path.  A real ANSI
                        # terminal uses isolated output and input regions instead.
                        self.renderer.write_system("running; Ctrl+C cancels in an interactive terminal\n")
                        await self._wait_for_run(wait)
                if self._inline_display is None:
                    self.renderer.finish_line()
                continue
            if command.name == "cancel":
                if command.arguments:
                    self.renderer.write_system("usage: /cancel\n")
                elif self.session.cancel():
                    self.renderer.write_system("cancellation requested; pending inputs cleared\n")
                else:
                    self.renderer.write_system("no active run\n")
                continue
            if command.name == "optimize" and isinstance(self.session, OptimizationClient):
                await self._optimization_frontend().run(command.arguments)
                continue
            if command.name in {"candidates", "candidate"}:
                self.renderer.write_system(f"unknown command: /{command.name}; use /optimize\n")
                continue
            if command.name == "config" and self.configuration is not None:
                if command.arguments:
                    self.renderer.write_system(
                        "usage: /config (opens the configuration menu)\n"
                    )
                    continue
                if getattr(self.session, "running", False) or getattr(
                    self.session,
                    "pending_count",
                    0,
                ):
                    self.renderer.write_system(
                        "finish or /cancel the active run before changing config\n"
                    )
                    continue
                if self._inline_display is not None:
                    self._suspend_inline_terminal()
                try:
                    with transient_screen(self.input, self.output):
                        result = TerminalConfigurationFrontend(
                            self.configuration,
                            input_stream=self.input,
                            output_stream=self.output,
                            line_editor=self.line_editor,
                            active_prompt_label=getattr(self.session.status, "prompt_label", ""),
                        ).run_for_active_session()
                    if result.start:
                        rebuild = getattr(self.session, "rebuild", None)
                        if rebuild is None:
                            self.renderer.write_system(
                                "configuration saved; the embedding host must open "
                                "a new runtime\n"
                            )
                            return 0
                        await rebuild()
                        self.configuration = getattr(
                            self.session,
                            "configuration",
                            self.configuration,
                        )
                    self._activate_inline_terminal()
                    if result.start:
                        self.renderer.write_system("\n[new session]\n")
                        self.renderer.show_welcome(self.session.status)
                finally:
                    if (
                        self._inline_display is not None
                        and not self._inline_display.active
                    ):
                        self._activate_inline_terminal()
                continue
            if command.name == "resume" and hasattr(self.session, "resume"):
                await self._resume(command.arguments)
                continue
            if command.name == "eval" and self.evaluation is not None:
                if command.arguments:
                    self.renderer.write_system("usage: /eval\n")
                    continue
                if getattr(self.session, "running", False) or getattr(
                    self.session, "pending_count", 0
                ):
                    self.renderer.write_system(
                        "finish or /cancel the active run before starting eval\n"
                    )
                    continue
                if self._inline_display is not None:
                    self._suspend_inline_terminal()
                try:
                    result = await TerminalEvaluationFrontend(
                        self.evaluation,
                        input_stream=self.input,
                        output_stream=self.output,
                        line_editor=self.line_editor,
                    ).run()
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    result = None
                    self.renderer.write_system(f"could not run evaluation: {exc}\n")
                finally:
                    if self._inline_display is not None:
                        self._activate_inline_terminal()
                if result is not None:
                    self.renderer.write_system(
                        f"\n[evaluation {result.status}: {result.evaluation_id}]\n"
                        f"report: {result.report_markdown}\n"
                        f"json: {result.report_json}\n"
                    )
                continue
            result = self.command_router.execute(command, self.session)
            if result.text:
                self.renderer.write_system(result.text)
            if result.should_exit:
                cancel = getattr(self.session, "cancel", None)
                if cancel is not None:
                    cancel()
                wait = getattr(self.session, "wait_until_idle", None)
                if wait is not None:
                    await wait()
                return 0

    def _authorization_pending(self):
        service = getattr(self.session, "authorization", None)
        return service.pending if service is not None else None

    async def _render_event(self, event):
        choices = getattr(self.line_editor, "set_choices", None)
        if isinstance(event, AuthorizationRequested):
            if choices is not None:
                choices(("1. Allow once", "2. Allow for this session", "3. Deny"), event.request_id)
        elif isinstance(event, AuthorizationResolved):
            if choices is not None:
                choices()
            if self._reading_authorization:
                self._reader_interrupt.set()
        await self.renderer.render(event)

    def _answer_authorization(self, line):
        service = getattr(self.session, "authorization", None)
        pending = self._authorization_pending()
        if service is None or pending is None:
            return
        text = line.strip()
        if text.startswith("\x00authorize:"):
            identity, text = text.removeprefix("\x00authorize:").split(":", 1)
            if identity != pending.request_id:
                return
        if text == "/cancel":
            self.session.cancel()
            return
        choice = {"": "once", "1": "once", "2": "session", "3": "deny", "deny": "deny", "\x1b": "deny"}.get(text)
        if choice is None:
            self.renderer.write_system("choose 1, 2, or 3; /cancel stops the run\n")
            return
        service.respond(pending.request_id, choice)

    async def _wait_for_run(self, wait):
        task = asyncio.create_task(wait())
        try:
            while not task.done():
                if self._authorization_pending() is not None:
                    self._reading_authorization = True
                    try:
                        line = await self._read_prompt_line()
                        if line is None:
                            self.session.cancel()
                        else:
                            self._answer_authorization(line)
                    except InputInterrupted as exc:
                        self._reader_interrupt.clear()
                        if not exc.handled:
                            self._handle_interrupt()
                    finally:
                        self._reading_authorization = False
                        self._reader_interrupt.clear()
                else:
                    await asyncio.wait({task}, timeout=0.05)
            await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    def _handle_interrupt(self) -> bool:
        now = time.monotonic()
        second = self._last_interrupt > 0 and now - self._last_interrupt <= 3.0
        self._last_interrupt = now
        if second:
            self.session.cancel()
            self._interrupt_exit = True
            self.renderer.write_system("exiting; stopping active work\n")
            return True
        if self.session.cancel():
            self.renderer.write_system("cancellation requested; pending inputs cleared. Press Ctrl+C again within 3s to exit.\n")
        else:
            self.renderer.write_system("input cleared. Press Ctrl+C again within 3s to exit, or use /exit.\n")
        return False

    def _signal_interrupt(self):
        self._handle_interrupt()
        self._reader_interrupt.set()
        interrupt = getattr(self.line_editor, "interrupt", None)
        if interrupt is not None:
            interrupt()

    def _read_line(self):
        try:
            return self.line_editor.read_line()
        except KeyboardInterrupt as exc:
            raise InputInterrupted from exc

    async def _read_prompt_line(self):
        if self._inline_display is None:
            # The fallback line editor owns the cursor until input is submitted.
            return await asyncio.to_thread(self._read_line)
        reader = asyncio.create_task(asyncio.to_thread(self._read_line))
        try:
            while not reader.done():
                await asyncio.wait({reader}, timeout=0.5)
                self._show_optimization_activity()
                self._show_optimization_notice()
                self._show_candidate_notice()
            return await reader
        finally:
            if not reader.done():
                interrupt = getattr(self.line_editor, "interrupt", None)
                if interrupt is not None:
                    interrupt()
                reader.cancel()

    def _show_optimization_activity(self):
        progress = getattr(self.session, "optimization_progress", None)
        if progress is None or progress.status != "running" or progress.activity is None:
            return
        identity = (progress.sequence, progress.activity)
        if identity == self._last_optimization_activity:
            return
        self._last_optimization_activity = identity
        self.renderer.write_system("[optimization] " + safe_terminal_text(format_optimization_activity(progress.activity)) + "\n")

    def _show_optimization_notice(self):
        progress = getattr(self.session, "optimization_progress", None)
        if progress is None or progress.status in {"idle", "running"} or progress.sequence == self._last_optimization_notice:
            return
        self._last_optimization_notice = progress.sequence
        self.renderer.write_system(f"Optimization {progress.status}" +
                                   (f": {safe_terminal_text(progress.error)}" if progress.error else "") + "\n")

    def _show_candidate_notice(self) -> None:
        if getattr(self.session, "running", False) or getattr(self.session, "pending_count", 0):
            return
        peek = getattr(self.session, "candidate_notice", None)
        acknowledge = getattr(self.session, "acknowledge_candidate_notice", None)
        if peek is None or acknowledge is None:
            return
        try:
            candidate_ids = peek()
            if candidate_ids:
                self.renderer.write_system(
                    f"\n[{len(candidate_ids)} candidate(s) ready; not active. "
                    "Use /optimize to review.]\n"
                )
                acknowledge(candidate_ids)
        except (OSError, ValueError, RuntimeError) as exc:
            self.renderer.write_system(f"candidate notice unavailable: {exc}\n")

    def _optimization_frontend(self) -> TerminalOptimizationFrontend:
        return TerminalOptimizationFrontend(
            self.session, self.renderer, self.line_editor, self.menu_input, self.menu_renderer,
        )

    async def _resume(self, arguments: tuple[str, ...]) -> None:
        if getattr(self.session, "running", False) or getattr(
            self.session,
            "pending_count",
            0,
        ):
            self.renderer.write_system(
                "finish or /cancel the active run before resuming another session\n"
            )
            return

        path: Path | None = None
        if arguments:
            value = " ".join(arguments)
            path = Path(value)
            if not path.is_absolute():
                path = Path(self.session.status.working_directory) / path
            path = path.resolve()
        else:
            discover = getattr(self.session, "resumable_sessions", None)
            if discover is None:
                self.renderer.write_system(
                    "the /resume session picker is unavailable in this frontend\n"
                )
                return
            try:
                sessions = discover()
            except (
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as exc:
                self.renderer.write_system(f"could not list sessions: {exc}\n")
                return
            if not sessions:
                self.renderer.write_system(
                    "no compatible non-empty sessions are available\n"
                )
                return
            if self._inline_display is not None:
                self._suspend_inline_terminal()
            try:
                with transient_screen(self.input, self.output):
                    selected = TerminalResumeFrontend(
                        sessions,
                        input_stream=self.input,
                        output_stream=self.output,
                        line_editor=self.line_editor,
                    ).run()
                path = Path(selected.path) if selected is not None else None
            finally:
                if self._inline_display is not None:
                    self._activate_inline_terminal()

        if path is None:
            return
        try:
            await self.session.resume(path)
        except (
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            self.renderer.write_system(f"could not resume session: {exc}\n")
            return
        self.configuration = getattr(
            self.session,
            "configuration",
            self.configuration,
        )
        self.renderer.write_system(f"\n[resumed {path}]\n")
        self.renderer.show_welcome(self.session.status)

        await self._show_history()

    async def _show_history(self) -> None:
        # History is optional for existing embedding hosts implementing TerminalSession.
        conversation = getattr(self.session, "conversation", None)
        if callable(conversation):
            await self.renderer.show_history(conversation())

    def _activate_inline_terminal(self) -> None:
        if self._inline_display is None:
            return
        start = getattr(self.line_editor, "start", None)
        if start is not None:
            start()
        self._inline_display.activate()

    def _suspend_inline_terminal(self) -> None:
        if self._inline_display is None:
            return
        try:
            self._inline_display.suspend()
        finally:
            stop = getattr(self.line_editor, "stop", None)
            if stop is not None:
                stop()



__all__ = ["TerminalFrontend"]
