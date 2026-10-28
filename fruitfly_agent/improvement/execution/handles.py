"""Owned task handles and a truthful adapter for final-only runners."""
from __future__ import annotations
import asyncio
from fruitfly_agent.improvement.execution.events import EventJournal
from fruitfly_agent.improvement.execution.control import ControlDispatcher
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord


class ManagedExecution:
    capabilities = frozenset({'events', 'stop'})

    def __init__(self, execute, *, execution_id, version_id, artifacts, record=None, process_events=False):
        self.task: asyncio.Task[ExecutionRecord]
        self.journal = EventJournal(execution_id, version_id, artifacts, record=record)
        self.dispatcher = ControlDispatcher(lambda: self.journal.position, {'stop': self.stop}, record=record,
            active=lambda: not self.task.done())
        self.stopped = False
        self.process_events = process_events
        self.task = asyncio.create_task(self.run(execute))

    async def run(self, execute):
        try:
            self.journal.publish('started', process_events=self.process_events)
            result = await execute(self.journal)
            self.journal.publish('finished', status=result.status, model_calls=result.model_calls)
            return result
        except asyncio.CancelledError:
            self.journal.publish('cancelled', requested=self.stopped)
            raise
        except Exception as exc:
            self.journal.publish('failed', error=type(exc).__name__)
            raise
        finally:
            self.journal.close()

    async def stop(self, request):
        if self.task.done():
            raise ValueError('execution is already finished')
        self.stopped = True
        self.task.cancel()

    def events(self):
        return self.journal.events()

    async def result(self):
        return await asyncio.shield(self.task)

    async def control(self, request):
        return await self.dispatcher.apply(request)

    async def aclose(self):
        if not self.task.done():
            self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)


class CompletionOnlyRunner:
    """Wrap execute-only backends; exposes no invented intermediate events."""
    def __init__(self, runner, artifacts, record=None):
        self.runner, self.artifacts, self.record = runner, artifacts, record
        self.capabilities = frozenset(getattr(runner, 'capabilities', ()))
        self.execution_charge = getattr(runner, 'execution_charge', 1)

    async def start(self, plan, task, harness):
        from uuid import uuid4
        async def execute(journal):
            return await self.runner.execute(plan, task, harness)
        return ManagedExecution(execute, execution_id='execution-' + uuid4().hex,
            version_id=harness.snapshot_id, artifacts=self.artifacts, record=self.record)

    async def execute(self, plan, task, harness):
        return await self.runner.execute(plan, task, harness)
