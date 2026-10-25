"""One evidence-driven workflow; generators and execution are injected ports."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import replace
import time
import inspect

from ..contracts.pipeline import (CandidateBundle, CompositionRequest, HarnessSnapshot,
    ImprovementOutcome, ProposalRequest, SelectionDecision, ExecutionRecord, Measurement)


from .budget import BudgetScope, AllocationExhausted, operation_deadline
from .stopping import BoundedStopPolicy, SearchState


class WorkflowServices:
    """Job-local accounting and cancellation. Editor receives a restricted view."""
    def __init__(self, plan, *, edit=None, complete=None, record=None, signal=None, budget=None):
        self.plan, self.editor = plan, edit
        self.completer = complete
        self.sink = record or (lambda event, **fields: None)
        self.budget = budget or BudgetScope({'model': plan.max_model_calls, 'execution': plan.max_executions}, signal=signal)
        self.signal = self.budget.signal
        self.used = self.budget.used
        self.events = []
        self.resources = []
        self.verification_budget = None

    def own(self, resource):
        if all(item is not resource for item in self.resources):
            self.resources.append(resource)
        return resource

    async def close(self):
        """Close owned optional async resources, even after cancellation."""
        try:
            for resource in reversed(tuple(self.resources)):
                await self.release(resource)
        finally:
            self.budget.close()

    async def release(self, resource):
        if not any(item is resource for item in self.resources):
            return
        self.resources = [item for item in self.resources if item is not resource]
        close = getattr(resource, 'aclose', None)
        if close is not None:
            try:
                await asyncio.wait_for(close(), timeout=min(self.plan.operation_timeout, 10))
            except Exception as exc:
                self.record('cleanup-failed', resource=type(resource).__qualname__, error=type(exc).__name__)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *error):
        await self.close()

    def check(self):
        self.budget.check()

    def reserve(self, kind, amount=1):
        self.budget.reserve(kind, amount)

    @contextmanager
    def phase(self, budget):
        previous = self.budget
        self.budget = budget
        try:
            yield
        finally:
            self.budget = previous

    def protect_verification(self, limits):
        self.verification_budget = self.budget.child(limits)

    def record(self, event, **fields):
        self.events.append((event, fields))
        self.sink(event, **fields)

    async def edit(self, stage, request):
        self.check()
        if self.editor is None:
            raise ValueError('this generator requires an editor capability')
        return await self.editor(stage, request, self)

    async def complete(self, system, prompt):
        if self.completer is None:
            raise ValueError('this generator requires a model completion capability')
        self.reserve('model')
        self.record('generator-model-request')
        result = await self.operation(self.completer(system, prompt, signal=self.signal))
        self.record('generator-model-response', text=result)
        return result

    async def operation(self, awaitable):
        try:
            self.check()
        except BaseException:
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            raise
        deadline = min(time.monotonic() + self.plan.operation_timeout,
                       self.budget.deadline or float('inf'), operation_deadline.get() or float('inf'))
        token = operation_deadline.set(deadline)
        try:
            work = asyncio.ensure_future(awaitable)
        finally:
            operation_deadline.reset(token)
        cancelled = asyncio.create_task(self.signal.wait())
        try:
            timeout = max(0, deadline - time.monotonic())
            done, _ = await asyncio.wait((work, cancelled), timeout=timeout,
                                         return_when=asyncio.FIRST_COMPLETED)
            self.check()
            if work not in done:
                raise TimeoutError('improvement operation timed out')
            return await work
        finally:
            work.cancel()
            cancelled.cancel()
            await asyncio.gather(work, cancelled, return_exceptions=True)


class GeneratorServices:
    """A generator may edit and record; it cannot execute, verify or activate."""
    def __init__(self, services):
        self.services = services

    def check(self):
        self.services.check()

    def record(self, event, **fields):
        self.services.record(event, **fields)

    async def edit(self, stage, request):
        if stage not in {'propose', 'compose'}:
            raise ValueError('candidate editing stage is required')
        return await self.services.edit(stage, request)

    async def complete(self, system, prompt):
        return await self.services.complete(system, prompt)

