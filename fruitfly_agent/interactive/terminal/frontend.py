"""Input loop for the built-in line-oriented terminal adapter."""

from __future__ import annotations

import asyncio
import sys
import signal
import time
import threading
from typing import TextIO, Mapping
from contextlib import contextmanager

from fruitfly_agent.interactive.contracts.events import AuthorizationRequested, AuthorizationResolved
from fruitfly_agent.interactive.terminal.bindings import TerminalBindings, TerminalSession, ImprovementClients
from fruitfly_agent.interactive.terminal.commands import TerminalCommandRegistry, TerminalCommandHandler
from fruitfly_agent.interactive.terminal.features.assembly import bind_commands
from fruitfly_agent.interactive.terminal.notifications import ImprovementNotifications

from fruitfly_agent.interactive.contracts.configuration import ConfigurationController
from fruitfly_agent.interactive.interaction.commands import CommandRouter, parse_command
from fruitfly_agent.interactive.terminal.io.input import LineEditor, create_line_editor, PollingLineEditor
from fruitfly_agent.interactive.terminal.io.live import (
    InlineTerminalDisplay,
    create_inline_terminal,
    InputInterrupted,
)
from fruitfly_agent.interactive.terminal.rendering.renderer import TerminalRenderer
from fruitfly_agent.interactive.terminal.io.screen import transient_screen
from fruitfly_agent.interactive.terminal.features.improvement.menu import TerminalImprovementFrontend


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
        command_handlers: Mapping[str, TerminalCommandHandler] | None = None,
        bindings: TerminalBindings | None = None,
        improvement_clients: ImprovementClients | None = None,
    ) -> None:
        self.session = session
        self._last_interrupt = 0.0
        self._interrupt_exit = False
        self._reader_interrupt = threading.Event()
        self._signal_installed = False
        self._previous_sigint = None
        self.input = input_stream or sys.stdin
        self.output = output_stream or sys.stdout
        self._inline_display: InlineTerminalDisplay | None = None
        if renderer is None and line_editor is None:
            isolated = create_inline_terminal(self.input, self.output, fullscreen=True)
            if isolated is not None:
                self._inline_display, line_editor = isolated
                renderer = TerminalRenderer(self._inline_display)
        self.renderer = renderer or TerminalRenderer(self.output)
        self.line_editor = line_editor or create_line_editor(self.input, self.output)
        if command_router is not None and configuration is not None:
            raise ValueError("pass command_router or configuration, not both")
        self.bindings = bindings or TerminalBindings.from_session(session)
        self._configuration_override = configuration
        self._improvement_clients = improvement_clients
        self.menu_input = None
        self.menu_renderer = None
        if (improvement_clients or ImprovementClients.from_session(session)).available:
            from fruitfly_agent.interactive.terminal.io.menu import create_menu_input, TerminalMenuRenderer
            self.menu_input = create_menu_input(self.input, self.output, self.line_editor)
            self.menu_renderer = TerminalMenuRenderer(self.output)
        self.command_router = command_router or CommandRouter()
        self._reading_authorization = False
        self.session.set_event_sink(self._render_event)
        self.commands = TerminalCommandRegistry()
        bind_commands(
            self.commands, bindings=self.bindings, configuration=lambda: self.configuration,
            status=lambda: self.session.status, cancel=self.bindings.cancel,
            menu_scope=self.menu_scope, input_stream=self.input, output_stream=self.output,
            line_editor=lambda: self.line_editor, write=self.renderer.write_system,
            welcome=self.renderer.show_welcome, show_history=self.show_history,
            improvement_frontend=self.improvement_frontend if self.menu_input is not None else None,
        )
        for name, handler in (command_handlers or {}).items():
            self.commands.register(name, handler)
        self._notifications = ImprovementNotifications(
            progress=self.bindings.progress, notice=self.bindings.candidate_notice,
            acknowledge=self.bindings.acknowledge_notice, busy=self.bindings.busy,
            write=self.renderer.write_system,
        )

    async def run(self) -> int:
        try:
            self._activate_inline_terminal()
            if self.input is sys.stdin and self.input.isatty():
                self._previous_sigint = signal.getsignal(signal.SIGINT)
                asyncio.get_running_loop().add_signal_handler(signal.SIGINT, self._signal_interrupt)
                self._signal_installed = True
                if self._inline_display is None:
                    self.line_editor = PollingLineEditor(self.input, self.output, self._reader_interrupt)
            enable = self.bindings.enable_authorization
            if enable is not None:
                enable(bool(self.input.isatty()))
            self.renderer.show_welcome(self.session.status)
            await self.show_history()
            self._notifications.show_candidates()
            return await self._run_loop()
        finally:
            enable = self.bindings.enable_authorization
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
            self._notifications.show()
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
                wait = self.bindings.wait
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
                if self.session.running and self.session.steer(text):
                    self.renderer.write_system("message added to current run\n")
                    continue
                enqueue = self.bindings.enqueue
                if enqueue is None:
                    task = asyncio.create_task(self.session.submit(text))
                    self.renderer.write_system("running; Ctrl+C cancels in an interactive terminal\n")
                    await task
                else:
                    was_running = self.session.running
                    try:
                        position = enqueue(text)
                    except (RuntimeError, ValueError) as exc:
                        self.renderer.write_system(f"cannot submit: {exc}\n")
                        continue
                    if was_running or position > 1:
                        self.renderer.write_system(
                            f"queued prompt ({position} pending)\n"
                        )
                    wait = self.bindings.wait
                    if wait is not None and self._inline_display is None:
                        # A readline frame and streamed model output cannot safely
                        # own the same cursor in the fallback path.  A real ANSI
                        # terminal uses isolated output and input regions instead.
                        self.renderer.write_system("running; Ctrl+C cancels in an interactive terminal\n")
                        await self._wait_for_run(wait)
                if self._inline_display is None:
                    self.renderer.finish_line()
                continue
            result = await self.commands.execute(command)
            if result is None:
                result = self.command_router.execute(command, self.session)
            self.renderer.write_command_result(result)
            if result.should_exit:
                self.bindings.cancel()
                wait = self.bindings.wait
                if wait is not None:
                    await wait()
                return 0

    def _authorization_pending(self):
        service = self.bindings.authorization()
        return service.pending if service is not None else None

    async def _render_event(self, event):
        choices = getattr(self.line_editor, "set_choices", None)
        if isinstance(event, AuthorizationRequested):
            if choices is not None:
                choices(("1. Allow once (Enter)", "2. " + event.session_label, "3. Deny (Esc)"), event.request_id)
        elif isinstance(event, AuthorizationResolved):
            if choices is not None:
                choices()
            if self._reading_authorization:
                self._reader_interrupt.set()
        await self.renderer.render(event)

    def _answer_authorization(self, line):
        service = self.bindings.authorization()
        pending = self._authorization_pending()
        if service is None or pending is None:
            return
        text = line.strip()
        if text.startswith("\x00authorize:"):
            identity, text = text.removeprefix("\x00authorize:").split(":", 1)
            if identity != pending.request_id:
                return
        if text == "/cancel":
            self.bindings.cancel()
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
                            self.bindings.cancel()
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
            self.bindings.cancel()
            self._interrupt_exit = True
            self.renderer.write_system("exiting; stopping active work\n")
            return True
        if self.bindings.cancel():
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
                self._notifications.show()
            return await reader
        finally:
            if not reader.done():
                interrupt = getattr(self.line_editor, "interrupt", None)
                if interrupt is not None:
                    interrupt()
                reader.cancel()

    def show_notifications(self) -> None:
        self._notifications.show()

    @property
    def configuration(self):
        return self._configuration_override or self.bindings.configuration()

    @contextmanager
    def menu_scope(self):
        """Lend terminal input/display to one menu and restore it on every exit."""
        self._suspend_inline_terminal()
        try:
            with transient_screen(self.input, self.output):
                yield
        finally:
            self._activate_inline_terminal()

    def improvement_frontend(self) -> TerminalImprovementFrontend:
        return TerminalImprovementFrontend(
            self.session, self.renderer, self.line_editor, self.menu_input, self.menu_renderer,
            clients=self._improvement_clients,
        )

    async def show_history(self) -> None:
        # History is optional for existing embedding hosts implementing TerminalSession.
        conversation = self.bindings.conversation
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
