"""Bound external context work without swallowing cancellation or hanging cleanup."""
import asyncio
from ..errors import FatalError


async def bounded_call(awaitable, *, timeout, signal=None):
    if signal is not None and signal.is_set():
        if hasattr(awaitable, 'close'):
            awaitable.close()
        raise asyncio.CancelledError
    work = asyncio.ensure_future(awaitable)
    cancel = asyncio.create_task(signal.wait()) if signal is not None else None
    tasks = tuple(t for t in (work, cancel) if t is not None)
    try:
        done, _ = await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        if work not in done:
            raise TimeoutError('context operation timed out')
        return await work
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        _, pending = await asyncio.wait(tasks, timeout=.1)
        for task in tasks:
            if task.done() and not task.cancelled():
                task.exception()
        if pending:
            for task in pending:
                task.add_done_callback(lambda finished: None if finished.cancelled() else finished.exception())
            raise FatalError('context operation cancellation unconfirmed', details={'kind': 'unconfirmed_cancellation'})
