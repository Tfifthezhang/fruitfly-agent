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
from fruitfly_agent.interactive.terminal.bindings import TerminalBindings, TerminalSession
from fruitfly_agent.interactive.terminal.commands import TerminalCommandRegistry, TerminalCommandHandler, effective_commands, complete_command
from fruitfly_agent.interactive.contracts.commands import CommandDescription, CommandResult, command_help_result
from fruitfly_agent.interactive.terminal.features.assembly import bind_commands
from fruitfly_agent.interactive.terminal.features.composer import Composer

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
    ) -> None:
        self.session = session
        self._history_snapshot = ()
        self._history_before = 0
        self._last_interrupt = 0.0
        self._interrupt_exit = False
        self._reader_interrupt = threading.Event()
        self._signal_installed = False
        self._previous_sigint = None
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
        self.bindings = bindings or TerminalBindings.from_session(session)
        self._configuration_override = configuration
        self.command_router = command_router or CommandRouter()
        self._reading_authorization = False
        self.session.set_event_sink(self._render_event)
        self.commands = TerminalCommandRegistry()
        self._composer = Composer(self.bindings.load_attachment, self.bindings.clipboard_image)
        self._composer_session: str | None = None
        configure_input = getattr(self.line_editor, 'set_input_adapter', None)
        if callable(configure_input):
            configure_input(self._composer)
        bind_commands(
            self.commands, bindings=self.bindings, configuration=lambda: self.configuration,
            status=lambda: self.session.status, cancel=self._cancel_input,
            menu_scope=self.menu_scope, input_stream=self.input, output_stream=self.output,
            line_editor=lambda: self.line_editor, write=self.renderer.write_system,
            welcome=self.renderer.show_welcome, show_history=self.show_history,
        )
        for name, handler in (command_handlers or {}).items():
            self.commands.register(name, handler)
        if self.command_router.uses_default_help and not any(item.name == 'help' for item in self.commands.descriptions()):
            help_description = next(item for item in self.command_router.descriptions() if item.name == 'help')
            self.commands.register('help', lambda command: command_help_result(self.command_descriptions(), command.arguments),
                summary=help_description.summary)
        configure_completion = getattr(self.line_editor, 'set_completion_provider', None)
        if self._inline_display is not None and callable(configure_completion):
            configure_completion(lambda query: complete_command(query, self.command_descriptions()))

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
            current_session = self.session.status.session_path
            if current_session != self._composer_session:
                if self._composer.pending:
                    self.renderer.write_system('Session changed; pending attachments and unsent draft cleared.\n')
                self._composer.clear()
                self._composer_session = current_session
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
            if not text and not self._composer.pending:
                continue
            if self._inline_display is not None:
                self.renderer.write_user_input(submitted)
            command = parse_command(text)
            if command is None:
                try:
                    content = self._composer.prepare(submitted)
                    validate = self.bindings.validate_input
                    if validate is not None:
                        validate(content)
                    if self.session.running and self.session.steer(content):
                        self._composer.clear()
                        self.renderer.write_system("message added to current run\n")
                        continue
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    self.renderer.write_system(f'cannot submit: {exc}. Draft retained; edit the input or press Enter to retry.\n')
                    continue
                enqueue = self.bindings.enqueue
                if enqueue is None:
                    task = asyncio.create_task(self.session.submit(content))
                    self.renderer.write_system("running; Ctrl+C cancels in an interactive terminal\n")
                    try:
                        await task
                    except (OSError, RuntimeError, TypeError, ValueError) as exc:
                        self.renderer.write_system(f'cannot submit: {exc}. Draft retained.\n')
                        continue
                    self._composer.clear()
                else:
                    was_running = self.session.running
                    try:
                        position = enqueue(content)
                    except (RuntimeError, ValueError) as exc:
                        self.renderer.write_system(f"cannot submit: {exc}\n")
                        continue
                    self._composer.clear()
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
            self._composer.release_command(submitted)
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

    def _cancel_input(self) -> bool:
        self._composer.clear()
        return self.bindings.cancel()

    def _handle_interrupt(self) -> bool:
        self._composer.clear()
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
                return await reader
        finally:
            if not reader.done():
                interrupt = getattr(self.line_editor, "interrupt", None)
                if interrupt is not None:
                    interrupt()
                reader.cancel()

    def command_descriptions(self) -> tuple[CommandDescription, ...]:
        return effective_commands(self.command_router.descriptions(), self.commands.descriptions())

    @property
    def configuration(self):
        return self._configuration_override or self.bindings.configuration()

    @contextmanager
    def menu_scope(self):
        """Lend terminal input/display to one menu and restore it on every exit."""
        self._suspend_inline_terminal(preserve_output=True)
        try:
            with transient_screen(self.input, self.output):
                yield
        finally:
            self._activate_inline_terminal()

    async def show_history(self, *, older: bool = False) -> None:
        # History is optional for existing embedding hosts implementing TerminalSession.
        conversation = self.bindings.conversation
        if callable(conversation):
            if not older:
                self._history_snapshot = conversation()
                self._history_before = len(self._history_snapshot)
            end = self._history_before
            start = max(0, end - 40)
            await self.renderer.show_history(self._history_snapshot[start:end])
            self._history_before = start
            if start:
                self.renderer.write_system(f'[messages {start + 1}–{end} of {len(self._history_snapshot)}; /history older for previous messages]\n')
            elif older:
                self.renderer.write_system('[start of saved history]\n')

    def _activate_inline_terminal(self) -> None:
        if self._inline_display is None:
            return
        start = getattr(self.line_editor, "start", None)
        if start is not None:
            start()
        self._inline_display.activate()

    def _suspend_inline_terminal(self, *, preserve_output: bool = False) -> None:
        if self._inline_display is None:
            return
        try:
            self._inline_display.suspend(preserve_output=preserve_output)
        finally:
            stop = getattr(self.line_editor, "stop", None)
            if stop is not None:
                stop()



__all__ = ["TerminalFrontend"]
