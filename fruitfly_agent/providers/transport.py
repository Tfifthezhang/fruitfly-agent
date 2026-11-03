"""Shared adapter deadlines, cancellation, and retry activity (no SDK imports)."""
from __future__ import annotations
from dataclasses import replace

import asyncio
from dataclasses import asdict, dataclass
import math
import random
import time

from fruitfly_agent.core.errors import FatalError, RetryableError, TaggedError
from fruitfly_agent.core.observation import FailureInfo, bind_observation, current_observation, operation, start_operation
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
    def __init__(self, policy, total_deadline, *, context=None):
        self.context = context or current_observation()
        self.policy = policy
        self.total_deadline = total_deadline
        self.progress_deadline = time.monotonic() + policy.first_progress_timeout
        self.saw_progress = False
        self.phase = 'prepare'
        with bind_observation(self.context):
            self.observed = start_operation('provider.' + self.phase, origin='provider')
            self.first_progress = start_operation('provider.first_progress', origin='provider')

    def switch_phase(self, phase):
        self.observed.finish()
        self.phase = phase
        with bind_observation(self.context):
            self.observed = start_operation('provider.' + phase, origin='provider')

    def note_error(self, exc):
        details = dict(exc.details) if isinstance(exc.details, dict) else {}
        diagnostics = dict(details.get('diagnostics', {}))
        diagnostics.setdefault('phase', self.phase)
        failure = details.get('failure')
        self.observed.fail(FailureInfo.from_dict(failure) if isinstance(failure, dict) else
            FailureInfo('provider', self.phase, details.get('timeout_kind', 'unknown'), 'runtime_rule'))
        exc.details = {**details, 'diagnostics': diagnostics}

    def progress(self):
        self.first_progress.finish()
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


async def close_transport(awaitable, timeout, *, deadline=None):
    # Cleanup has its own interval and allowance after the request expires.
    if deadline is not None:
        deadline.observed.finish()
    with operation("provider.cleanup", origin="provider") as observed:
        try:
            await bounded_wait(awaitable, None, time.monotonic() + timeout, "cleanup_timeout", timeout)
        except TaggedError as exc:
            failure = FailureInfo('provider', 'cleanup', 'cleanup_timeout', 'runtime_rule', effect_state='unknown')
            observed.fail(failure, state='cleanup_unconfirmed')
            exc.details = {**(exc.details or {}), 'failure': failure.to_dict(),
                'diagnostics': {'phase': 'cleanup', 'failure_category': 'cleanup_timeout', 'evidence_kind': 'runtime_rule'}}
            if deadline is not None:
                deadline.phase = 'cleanup'
            raise


async def attempts(provider, view, signal):
    policy = provider._policy
    total_deadline = time.monotonic() + policy.total_timeout
    failures = []
    for attempt in range(provider.retry_max + 1):
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        delivered = False
        started = time.monotonic()
        yield StreamActivity("waiting_model", attempt + 1, provider.retry_max + 1)
        attempt_scope = start_operation('provider.attempt', origin='provider')
        context = replace(current_observation(), parent_operation_id=attempt_scope.event.operation_id)
        deadline = AttemptDeadline(policy, total_deadline, context=context)
        terminal = False
        producer = provider._stream_once(view, signal, deadline=deadline)
        try:
            while True:
                try:
                    with bind_observation(context):
                        event = await anext(producer)
                except StopAsyncIteration:
                    break
                terminal = isinstance(event, StreamDone)
                if terminal and not deadline.saw_progress:
                    deadline.first_progress.state = 'skipped'
                if (not isinstance(event, (StreamActivity, StreamDone, StreamError))
                        or isinstance(event, StreamActivity) and bool(event.tool_name)):
                    delivered = True
                yield event
            if not deadline.saw_progress:
                deadline.first_progress.state = 'skipped'
            return
        except (asyncio.CancelledError, GeneratorExit):
            if terminal:
                raise
            attempt_scope.state = deadline.observed.state = 'cancelled'
            if not deadline.saw_progress:
                deadline.first_progress.state = 'cancelled'
            raise
        except TaggedError as exc:
            details = exc.details if isinstance(exc.details, dict) else {}
            diagnostics = dict(details.get('diagnostics', {}))
            diagnostics.setdefault('phase', deadline.phase)
            diagnostics.setdefault('failure_category', details.get('timeout_kind', 'unknown'))
            failure = FailureInfo('provider', diagnostics['phase'], diagnostics['failure_category'],
                diagnostics.get('evidence_kind', 'runtime_rule' if details.get('timeout_kind') else 'unknown'),
                'partial_delivery' if delivered else 'non_retryable' if not isinstance(exc, RetryableError) else 'retryable',
                'unknown')
            source_failure = details.get('failure')
            if isinstance(source_failure, dict):
                source = FailureInfo.from_dict(source_failure)
                failure = replace(failure, causes=source.causes, http_status=source.http_status, exception_type=source.exception_type)
            details['failure'] = failure.to_dict()
            attempt_scope.fail(failure)
            deadline.observed.fail(failure)
            if not deadline.saw_progress:
                deadline.first_progress.fail(failure)
            failures.append({'attempt': attempt + 1, 'operation_id': attempt_scope.event.operation_id, 'elapsed_seconds': time.monotonic() - started,
                             'error_kind': type(exc).__name__, 'status_code': details.get('status_code'),
                             'content_delivered': delivered, 'causes': diagnostics.get('causes', []),
                             'phase': diagnostics['phase'], 'failure_category': diagnostics['failure_category']})
            failures = failures[-8:]
            diagnostics.update(attempt_count=attempt + 1, attempts=list(failures))
            exc.details = {**details, 'diagnostics': diagnostics}
            deadline.observed.finish()
            deadline.first_progress.finish()
            attempt_scope.finish()
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
                with operation("provider.backoff", origin="provider"):
                    await bounded_wait(provider._sleep(delay, signal), signal, total_deadline,
                                       "total_timeout", policy.cleanup_timeout)
            except RetryableError as timeout:
                timeout.details = {**(timeout.details or {}), 'diagnostics': {**diagnostics, 'phase': 'backoff'},
                    'failure': FailureInfo('provider', 'backoff', 'total_timeout', 'runtime_rule', 'exhausted', 'unknown').to_dict()}
                yield StreamActivity("provider_timeout", attempt + 1, provider.retry_max + 1, error_kind="total_timeout")
                yield StreamError(timeout)
                return
        except Exception as exc:
            from .error_classification import classify_provider_error
            classified = classify_provider_error(exc)
            failure = replace(FailureInfo.from_dict(classified.details['failure']), stage=deadline.phase)
            attempt_scope.fail(failure)
            deadline.observed.fail(failure)
            if not deadline.saw_progress:
                deadline.first_progress.fail(failure)
            yield StreamError(FatalError(f"{type(exc).__name__}: {exc}", details={'failure': failure.to_dict()}))
            return
        finally:
            try:
                with bind_observation(context):
                    await producer.aclose()
            finally:
                deadline.observed.finish()
                deadline.first_progress.finish()
                attempt_scope.finish()


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
