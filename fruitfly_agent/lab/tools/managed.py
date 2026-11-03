"""Runtime-owned operations with bounded state, output and confirmed retirement."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import inspect
import logging
import math
import time
from uuid import uuid4

from fruitfly_agent.core.extensions.operations import OperationSupervisor, OperationCleanupError
from fruitfly_agent.core.observation import FailureInfo, current_observation, operation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ManagedStatus:
    handle: str
    state: str
    elapsed_seconds: float
    run_id: str
    tool_call_id: str


class ManagedOperations:
    def __init__(self, *, max_active=4, retained=128, output_characters=12000):
        if any(type(value) is not int or value <= 0 for value in (max_active, retained, output_characters)):
            raise ValueError('managed operation bounds must be positive integers')
        self.max_active, self.retained, self.output_characters = max_active, retained, output_characters
        self.jobs = {}
        self.closed = False
        self.listener = None
        self.supervisor = OperationSupervisor(retirement_timeout=.1)

    async def _notify(self, handle):
        job = self.jobs[handle]
        value = self.status(handle)
        if job.get('notified_state') == value.state:
            return
        job['notified_state'] = value.state
        if self.listener is not None:
            try:
                value = self.listener(value)
                if inspect.isawaitable(value):
                    await value
            except Exception:
                logger.warning('managed operation listener failed', exc_info=True)

    async def submit(self, work, *, signal=None, is_error=lambda result: False):
        if self.closed or self.supervisor.poisoned:
            raise ValueError('command manager is closed or cleanup is unconfirmed')
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        if sum(not job['task'].done() for job in self.jobs.values()) >= self.max_active:
            raise ValueError('active command allowance exhausted; poll or cancel an existing handle')
        while len(self.jobs) >= self.retained:
            key = next((key for key, job in self.jobs.items() if job['task'].done()), None)
            if key is None:
                raise ValueError('command handle allowance exhausted')
            self.jobs.pop(key)
        handle = 'command-' + uuid4().hex
        context = current_observation()
        job = {'task': None, 'watcher': None, 'output': '', 'started': time.monotonic(),
            'finished': None, 'state': 'running', 'run_id': context.run_id,
            'tool_call_id': context.tool_call_id}
        async def output(text):
            job['output'] = text[-self.output_characters:]
        async def invoke():
            try:
                with operation('tool.background', origin='tool') as observed:
                    result = await work(output)
                    job['state'] = 'failed' if is_error(result) else 'succeeded'
                    if job['state'] == 'failed':
                        observed.fail(FailureInfo('tool', 'tool.background', 'result.error', 'runtime_rule', effect_state='completed'))
                    return result
            except asyncio.CancelledError:
                job['state'] = 'cancelled'
                raise
            except Exception:
                job['state'] = 'failed'
                raise
            finally:
                job['finished'] = time.monotonic()
                await self._notify(handle)
        task = asyncio.create_task(invoke())
        job['task'] = task
        self.jobs[handle] = job
        if signal is not None:
            async def watch():
                await signal.wait()
                task.cancel()
            job['watcher'] = asyncio.create_task(watch())
        def finished(value):
            if not value.cancelled():
                value.exception()
            else:
                job['state'] = 'cancelled'
                job['finished'] = job['finished'] or time.monotonic()
            if job['watcher'] is not None:
                job['watcher'].cancel()
        task.add_done_callback(finished)
        await self._notify(handle)
        return handle

    def status(self, handle):
        if handle not in self.jobs:
            raise ValueError('unknown or retired command handle')
        job = self.jobs[handle]
        return ManagedStatus(handle, job['state'], max(0., (job['finished'] or time.monotonic()) - job['started']),
            job['run_id'], job['tool_call_id'])

    def statuses(self):
        return tuple(self.status(handle) for handle in self.jobs)

    async def wait(self, handle, seconds=0):
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 <= seconds <= 30:
            raise ValueError('wait_seconds must be finite and between 0 and 30')
        self.status(handle)
        task = self.jobs[handle]['task']
        if not task.done() and seconds:
            await asyncio.wait((task,), timeout=seconds)
        return self.jobs[handle]

    async def _retire(self, tasks):
        if not tasks:
            return
        try:
            await self.supervisor.run(lambda: asyncio.gather(*tasks, return_exceptions=True), timeout=10)
        except (TimeoutError, OperationCleanupError) as exc:
            for handle, job in self.jobs.items():
                if job['task'] in tasks and not job['task'].done():
                    job['state'] = 'cleanup_unconfirmed'
                    await self._notify(handle)
            raise RuntimeError('command cancellation was not confirmed') from exc

    async def cancel(self, handle):
        self.status(handle)
        task = self.jobs[handle]['task']
        task.cancel()
        await self._retire((task,))
        await self._notify(handle)
        return self.status(handle)

    async def close(self):
        if self.closed:
            if self.supervisor.poisoned:
                raise RuntimeError('command cancellation was not confirmed')
            return
        self.closed = True
        tasks = tuple(task for job in self.jobs.values() for task in (job['task'], job['watcher']) if task is not None)
        for task in tasks:
            task.cancel()
        await self._retire(tasks)
        for handle in self.jobs:
            await self._notify(handle)
