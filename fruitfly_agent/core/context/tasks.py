"""Context timeout adaptation over Core's shared cancellation supervisor."""
import asyncio
from ..errors import FatalError
from ..extensions.operations import OperationSupervisor, OperationCleanupError


async def bounded_call(awaitable, *, timeout, signal=None):
    if signal is not None and signal.is_set():
        if hasattr(awaitable, 'close'):
            awaitable.close()
        raise asyncio.CancelledError
    try:
        return await OperationSupervisor(retirement_timeout=.1).run(lambda: awaitable, timeout=timeout, signal=signal)
    except OperationCleanupError as exc:
        raise FatalError('context operation cancellation unconfirmed', details={'kind': 'unconfirmed_cancellation'}) from exc
