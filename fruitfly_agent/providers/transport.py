"""Shared adapter deadlines, cancellation, and retry activity (no SDK imports)."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import math
import random
import time

from fruitfly_agent.core.errors import FatalError, RetryableError, TaggedError
from fruitfly_agent.core.model_stream import StreamActivity, StreamDone, StreamError


@dataclass(frozen=True)
class TransportPolicy:
    connect_timeout: float = 10.0
    timeout: float = 600.0
    first_progress_timeout: float = 180.0
    stall_timeout: float = 180.0
    total_timeout: float = 900.0
    cleanup_timeout: float = 5.0
    retry_jitter: float = 0.2

    def __post_init__(self):
        for name, value in asdict(self).items():
            valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                     and math.isfinite(value) and (0 <= value <= 1 if name == "retry_jitter" else value > 0))
            if not valid:
                raise ValueError(f"{name} must be finite and {'between 0 and 1' if name == 'retry_jitter' else 'positive'}")
            object.__setattr__(self, name, float(value))


class AttemptDeadline:
    def __init__(self, policy, total_deadline):
        self.policy = policy
        self.total_deadline = total_deadline
        self.progress_deadline = time.monotonic() + policy.first_progress_timeout
        self.saw_progress = False

    def progress(self):
        self.saw_progress = True
        self.progress_deadline = time.monotonic() + self.policy.stall_timeout

    async def wait(self, operation, signal):
        deadline = min(self.total_deadline, self.progress_deadline)
        kind = ("total_timeout" if self.total_deadline <= self.progress_deadline else
                "stall_timeout" if self.saw_progress else "first_progress_timeout")
        return await bounded_wait(operation, signal, deadline, kind, self.policy.cleanup_timeout)


async def bounded_wait(operation, signal, deadline, kind, cleanup_timeout=5):
    task = asyncio.ensure_future(operation)
    abort = asyncio.create_task(signal.wait()) if signal is not None else None
    try:
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        if time.monotonic() >= deadline:
            raise RetryableError(f"Provider {kind}: waiting deadline exceeded; remote outcome and cost may be unknown",
                                 details={"timeout_kind": kind})
        watched = {task} if abort is None else {task, abort}
        done, _ = await asyncio.wait(watched, timeout=max(0, deadline - time.monotonic()),
                                     return_when=asyncio.FIRST_COMPLETED)
        # Prefer an acquired resource so its owner can close it in finally.
        if task in done:
            return task.result()
        if abort is not None and abort in done:
            raise asyncio.CancelledError
        raise RetryableError(f"Provider {kind}: waiting deadline exceeded; remote outcome and cost may be unknown",
                             details={"timeout_kind": kind})
    finally:
        if abort is not None:
            abort.cancel()
            await asyncio.gather(abort, return_exceptions=True)
        if not task.done():
            task.cancel()
            done, _ = await asyncio.wait({task}, timeout=cleanup_timeout)
            if not done:
                task.add_done_callback(_consume)
        if task.done():
            _consume(task)


def _consume(task):
    if not task.cancelled():
        task.exception()


async def close_transport(operation, timeout):
    # Cleanup has a separate, bounded allowance even after the request expires.
    await bounded_wait(operation, None, time.monotonic() + timeout, "cleanup_timeout", timeout)


async def attempts(provider, view, signal):
    policy = provider._policy
    total_deadline = time.monotonic() + policy.total_timeout
    for attempt in range(provider.retry_max + 1):
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        delivered = False
        yield StreamActivity("waiting_model", attempt + 1, provider.retry_max + 1)
        producer = provider._stream_once(view, signal, deadline=AttemptDeadline(policy, total_deadline))
        try:
            async for event in producer:
                if not isinstance(event, (StreamActivity, StreamDone, StreamError)):
                    delivered = True
                yield event
            return
        except asyncio.CancelledError:
            raise
        except TaggedError as exc:
            details = exc.details if isinstance(exc.details, dict) else {}
            kind = details.get("timeout_kind", type(exc).__name__)
            if details.get("timeout_kind"):
                yield StreamActivity("provider_timeout", attempt + 1, provider.retry_max + 1, error_kind=kind)
            if (not isinstance(exc, RetryableError) or delivered or attempt >= provider.retry_max
                    or kind in {"total_timeout", "cleanup_timeout"}):
                yield StreamError(exc)
                return
            delay = provider.retry_base_delay * (2 ** attempt)
            retry_after = details.get("retry_after")
            if isinstance(retry_after, (int, float)) and math.isfinite(retry_after) and retry_after >= 0:
                delay = max(delay, retry_after)
            delay += random.uniform(0, delay * policy.retry_jitter)
            yield StreamActivity("provider_retrying", attempt + 1, provider.retry_max + 1,
                                 delay, kind, details.get("status_code"))
            try:
                await bounded_wait(provider._sleep(delay, signal), signal, total_deadline,
                                   "total_timeout", policy.cleanup_timeout)
            except RetryableError as timeout:
                yield StreamActivity("provider_timeout", attempt + 1, provider.retry_max + 1, error_kind="total_timeout")
                yield StreamError(timeout)
                return
        except Exception as exc:
            yield StreamError(FatalError(f"{type(exc).__name__}: {exc}"))
            return
        finally:
            await producer.aclose()


def retry_details(exc: Exception, error: TaggedError):
    """Retain a bounded retry hint, without exposing response headers or keys."""
    from email.utils import parsedate_to_datetime
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is None:
        return error
    raw = headers.get("retry-after")
    if raw is None:
        return error
    try:
        delay = float(raw)
    except (TypeError, ValueError):
        try:
            delay = parsedate_to_datetime(raw).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            return error
    if math.isfinite(delay):
        error.details = {**(error.details or {}), "retry_after": max(0, delay)}
    return error


def validate_retries(retry_max, retry_base_delay):
    if isinstance(retry_max, bool) or not isinstance(retry_max, int) or retry_max < 0:
        raise ValueError("retry_max must be a nonnegative integer")
    if isinstance(retry_base_delay, bool) or not isinstance(retry_base_delay, (int, float)) or not math.isfinite(retry_base_delay) or retry_base_delay < 0:
        raise ValueError("retry_base_delay must be finite and nonnegative")
