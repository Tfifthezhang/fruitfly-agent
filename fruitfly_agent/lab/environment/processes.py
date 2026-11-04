"""Owned POSIX process groups and bounded live-output notifications."""
import asyncio
import os
import signal

from fruitfly_agent.core.extensions.operations import OperationSupervisor


class ProcessGroup:
    """Keep the group identity even after its leader has exited."""

    def __init__(self, process):
        self.process = process
        self.group_id = process.pid  # The caller must use start_new_session=True.

    def kill(self):
        try:
            os.killpg(self.group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass

    async def stop(self, *tasks):
        self.kill()
        # A later explicit close may confirm resources which retired after an
        # earlier deadline. The owning executor still blocks new execution.
        supervisor = OperationSupervisor(retirement_timeout=.1)
        try:
            await supervisor.run(
                lambda: asyncio.gather(self.process.wait(), *tasks, return_exceptions=True), timeout=2)
        except Exception as exc:
            raise RuntimeError('process group cleanup could not be confirmed') from exc


class OutputNotifications:
    """Best-effort display updates; complete output stays with the executor.

    Slow consumers may miss intermediate chunks. At most sixteen pending chunks
    are retained, and shutdown has a separate 0.1-second flush allowance.
    """

    def __init__(self):
        self.queue = asyncio.Queue(maxsize=16)
        self.owner = asyncio.current_task()
        self.closing = False
        self.supervisor = OperationSupervisor(retirement_timeout=.1)
        self.worker = asyncio.create_task(self._run())
        self.worker.add_done_callback(self._finished)

    def _finished(self, task):
        if task.cancelled() and not self.closing:
            self.owner.cancel()

    def publish(self, callback, text):
        if callback is None or not text:
            return
        if self.queue.full():
            self.queue.get_nowait()
            self.queue.task_done()
        self.queue.put_nowait((callback, text))

    async def _run(self):
        while not self.closing or not self.queue.empty():
            callback, text = await self.queue.get()
            try:
                await callback(text)
            except Exception:
                pass
            finally:
                self.queue.task_done()

    async def close(self):
        self.closing = True
        if self.worker.done():
            return
        try:
            try:
                await self.supervisor.run(self.queue.join, timeout=.1)
            except TimeoutError:
                pass
        finally:
            self.worker.cancel()
            try:
                await self.supervisor.run(
                    lambda: asyncio.gather(self.worker, return_exceptions=True), timeout=.1)
            except Exception as exc:
                raise RuntimeError('output notification cleanup could not be confirmed') from exc
