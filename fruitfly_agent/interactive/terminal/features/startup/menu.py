"""Startup choices and cancellable waiting, without runtime construction."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import signal
import sys
from typing import TextIO

from fruitfly_agent.interactive.contracts.startup import StartupAction, StartupSnapshot
from fruitfly_agent.interactive.terminal.io.input import create_line_editor
from fruitfly_agent.interactive.terminal.io.live import InputInterrupted
from fruitfly_agent.interactive.terminal.io.menu import (
    LineMenuInput, MenuAction, MenuInput, MenuRow, TerminalMenuRenderer,
    create_menu_input, navigate_menu,
)


class TerminalStartupFrontend:
    def __init__(self, *, input_stream: TextIO | None = None,
                 output_stream: TextIO | None = None, menu_input: MenuInput | None = None) -> None:
        self.input = input_stream or sys.stdin
        self.output = output_stream or sys.stdout
        self.menu_input = menu_input or create_menu_input(
            self.input, self.output, create_line_editor(self.input, self.output))
        self.renderer = TerminalMenuRenderer(self.output)
        self.renderer.numbered = isinstance(self.menu_input, LineMenuInput)
        self._input_lock = asyncio.Lock()
        self._refresh_wait = False

    @asynccontextmanager
    async def lend_input(self) -> AsyncIterator[None]:
        """Suspend startup polling while a host confirmation owns terminal input."""
        async with self._input_lock:
            try:
                yield
            finally:
                self._refresh_wait = True

    def run(self, snapshot: StartupSnapshot, *, notice: str = '') -> StartupAction:
        selected = 0 if snapshot.ready else 1
        while True:
            self.renderer.render(title='FruitFlyAgent',
                subtitle=f'Model: {snapshot.model}\nEnvironment: {snapshot.environment}\n'
                    f'Session: {snapshot.session}\nStatus: ' +
                    ('Configuration complete · Connection not checked' if snapshot.ready else 'Configuration needs attention'),
                rows=(MenuRow('Start session', '' if snapshot.ready else 'Complete configuration first',
                              state='' if snapshot.ready else 'unavailable'),
                      MenuRow('Configure'), MenuRow('Exit')),
                selected=selected, notice=notice or '\n'.join(snapshot.warnings),
                instructions='↑↓ move · Enter select · q exit' if not self.renderer.numbered else
                    'Enter an option number; blank selects highlighted; q exits')
            try:
                event = self.menu_input.read_event()
            except (KeyboardInterrupt, InputInterrupted):
                return 'exit'
            selected, handled = navigate_menu(event, selected, 3)
            if handled:
                continue
            if event.action in {MenuAction.BACK, MenuAction.QUIT}:
                return 'exit'
            if event.action == MenuAction.ACTIVATE:
                if selected == 0 and not snapshot.ready:
                    selected = 1
                    continue
                return ('start', 'configure', 'exit')[selected]

    async def wait_for_start(self, task: asyncio.Task[None], *, environment: str) -> bool:
        """Cancel the supplied startup task, then wait for its owner's cleanup."""
        self.renderer.render(title='Starting session…', subtitle=f'Environment: {environment}',
            rows=(), selected=0, instructions='Ctrl+C to cancel')
        def cancel_start() -> None:
            # Repeated interrupts must not cancel the owner's cleanup a second time.
            if not task.done() and not task.cancelling():
                task.cancel()
        previous = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, lambda signum, frame: cancel_start())
        poll = getattr(self.menu_input, 'poll_event', None)
        try:
            while not task.done():
                if poll is None:
                    await asyncio.wait({task}, timeout=.1)
                else:
                    try:
                        async with self._input_lock:
                            if task.done():
                                break
                            if self._refresh_wait:
                                self.renderer.render(title='Starting session…', subtitle=f'Environment: {environment}',
                                    rows=(), selected=0, instructions='Ctrl+C to cancel')
                                self._refresh_wait = False
                            event = await asyncio.to_thread(poll, .1)
                        if event.action in {MenuAction.BACK, MenuAction.QUIT}:
                            cancel_start()
                    except (KeyboardInterrupt, InputInterrupted):
                        cancel_start()
            try:
                await task
            except asyncio.CancelledError:
                return False
            return True
        finally:
            signal.signal(signal.SIGINT, previous)
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
