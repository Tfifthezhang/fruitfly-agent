"""One evidence-driven workflow; generators and execution are injected ports."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import asdict, replace
import time
import inspect
from collections import deque
from typing import Any
from ..contracts.lifecycle import LifecycleEvent
from ..contracts.versions import canonical_json
from ..extensions.hooks import HookRegistry
from fruitfly_agent.core.extensions.operations import OperationSupervisor, consume as _consume_result
from ..contracts.failures import PersistenceError, CleanupError

from fruitfly_agent.improvement.contracts.candidates import CandidateBundle
from fruitfly_agent.improvement.contracts.editing import CompositionRequest, ProposalRequest
from fruitfly_agent.improvement.contracts.components import HarnessSnapshot
from fruitfly_agent.improvement.contracts.pipeline import ImprovementOutcome
from fruitfly_agent.improvement.contracts.assessment import SelectionDecision, Measurement
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord


from fruitfly_agent.improvement.workflow.budget import BudgetScope, AllocationExhausted, operation_deadline


class WorkflowServices:
    """Job-local accounting and cancellation. Editor receives a restricted view."""
    def __init__(self, plan, *, edit=None, complete=None, record=None, signal=None, budget=None, hooks=None):
        self.plan, self.editor = plan, edit
        self.completer = complete
        self.sink = record or (lambda event, **fields: None)
        self.budget = budget or BudgetScope({'model': plan.max_model_calls, 'execution': plan.max_executions}, signal=signal)
        self.signal = self.budget.signal
        self.used = self.budget.used
        self.events: deque[tuple[str, dict[str, Any]]] = deque(maxlen=256)
        self.hooks = hooks if hooks is not None else HookRegistry()
        self.state = None
        self.uncertain_model_allowance = 0
        self.resources = []
        self.verification_budget = None
        self.interrupted_records = []
        self.supervisor = OperationSupervisor(cleanup_error=CleanupError)

    def own(self, resource):
        if all(item is not resource for item in self.resources):
            self.resources.append(resource)
        return resource

    async def close(self):
        """Close owned optional async resources, even after cancellation."""
        errors = []
        try:
            for resource in reversed(tuple(self.resources)):
                try:
                    await self.release(resource)
                except (Exception, asyncio.CancelledError) as exc:
                    errors.append(exc)
        finally:
            self.budget.close()
        if errors:
            raise CleanupError('owned resource cleanup failed') from errors[0]

    async def release(self, resource):
        if not any(item is resource for item in self.resources):
            return
        self.resources = [item for item in self.resources if item is not resource]
        close = getattr(resource, 'aclose', None)
        if close is not None:
            try:
                task = asyncio.ensure_future(close())
                done, _ = await asyncio.wait((task,), timeout=10)
                if not done:
                    task.cancel()
                    task.add_done_callback(_consume_result)
                    raise CleanupError('resource cleanup did not confirm')
                await task
            except (Exception, asyncio.CancelledError) as exc:
                self.record('cleanup-failed', resource=type(resource).__qualname__, error=type(exc).__name__)
                raise CleanupError('resource cleanup failed') from exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *error):
        await self.close()

    def check(self):
        self.budget.check()

    def retain_execution(self, record):
        self.interrupted_records.append(record)
        self.record('execution-interrupted', receipt=asdict(record))

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
        if event == 'external-budget-settled' and fields.get('observed_calls') is None:
            self.uncertain_model_allowance += fields['charged_allowance']
        self.events.append((event, fields))
        try:
            self.sink(event, **fields)
        except Exception as exc:
            raise PersistenceError('workflow journal could not be persisted') from exc

    async def emit(self, name, payload=None):
        state = self.state
        value = {'model_calls': self.used['model'], 'executions': self.used['execution'], **(payload or {})}
        event = LifecycleEvent(name, self.plan.job_id, state.round_index if state else -1,
            state.phase if state else 'preparing', canonical_json(value))
        return await self.hooks.dispatch(event, self)

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
        if self.supervisor.poisoned:
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            raise CleanupError('previous stage retirement was not confirmed')
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
            return await self.supervisor.run(lambda: awaitable,
                timeout=max(0, deadline - time.monotonic()), signal=self.signal, check=self.check)
        except CleanupError:
            self.record('cleanup-unconfirmed', operation='stage')
            raise
        finally:
            operation_deadline.reset(token)



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

