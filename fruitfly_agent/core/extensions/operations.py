"""Bounded cooperative operations; unconfirmed retirement stops scheduling."""
import asyncio
import inspect
import math

class OperationCleanupError(RuntimeError):
    """Owned work could not be confirmed retired."""


def consume(task):
    if not task.cancelled():
        task.exception()


class OperationSupervisor:
    def __init__(self, *, retirement_timeout=10, cleanup_error=OperationCleanupError):
        if (isinstance(retirement_timeout, bool) or not isinstance(retirement_timeout, (int, float))
                or not math.isfinite(retirement_timeout) or retirement_timeout <= 0):
            raise ValueError('retirement timeout must be finite and positive')
        self.retirement_timeout = retirement_timeout
        self.cleanup_error = cleanup_error
        self.poisoned = False

    async def run(self, operation, *, timeout, signal=None, check=lambda: None):
        if self.poisoned:
            raise self.cleanup_error('previous operation retirement was not confirmed')
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
            raise ValueError('operation timeout must be finite and nonnegative')
        check()
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        async def invoke():
            value = operation()
            return await value if inspect.isawaitable(value) else value
        work = asyncio.create_task(invoke())
        cancelled = asyncio.create_task(signal.wait()) if signal is not None else None
        tasks = (work, cancelled) if cancelled is not None else (work,)
        try:
            done, _ = await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            check()
            if signal is not None and signal.is_set():
                raise asyncio.CancelledError
            if work not in done:
                raise TimeoutError('operation timed out')
            return await work
        finally:
            for task in tasks:
                task.cancel()
            done, pending = await asyncio.wait(tasks, timeout=self.retirement_timeout)
            for task in done:
                consume(task)
            if pending:
                self.poisoned = True
                for task in pending:
                    task.add_done_callback(consume)
                raise self.cleanup_error('operation cancellation did not confirm')
