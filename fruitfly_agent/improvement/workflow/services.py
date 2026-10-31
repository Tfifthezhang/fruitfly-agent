"""One evidence-driven workflow; generators and execution are injected ports."""
from __future__ import annotations

import asyncio
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


from .timing import StageClock, current_stage, stage_role


class WorkflowServices:
    """Job-local accounting and cancellation. Editor receives a restricted view."""
    def __init__(self, plan, *, edit=None, complete=None, record=None, signal=None, hooks=None):
        self.plan, self.editor = plan, edit
        self.completer = complete
        self.sink = record or (lambda event, **fields: None)
        self.signal = signal if signal is not None else asyncio.Event()
        self.used = {'model': 0, 'execution': 0}
        self.events: deque[tuple[str, dict[str, Any]]] = deque(maxlen=256)
        self.hooks = hooks if hooks is not None else HookRegistry()
        self.state = None
        self.resources = []
        self.interrupted_records = []
        self.evidence_builder = None
        self.hypotheses = {}
        self.supervisor = OperationSupervisor(cleanup_error=CleanupError)

    def own(self, resource):
        if all(item is not resource for item in self.resources):
            self.resources.append(resource)
        return resource

    async def close(self):
        """Close owned optional async resources, even after cancellation."""
        errors = []
        for resource in reversed(tuple(self.resources)):
            try:
                await self.release(resource)
            except (Exception, asyncio.CancelledError) as exc:
                errors.append(exc)
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
        if self.supervisor.poisoned:
            raise CleanupError('previous stage retirement was not confirmed')
        if self.signal.is_set():
            raise asyncio.CancelledError('improvement cancelled')
        clock = current_stage.get()
        if clock is not None and clock.owner is self:
            clock.check()

    def retain_execution(self, record):
        self.interrupted_records.append(record)
        self.record('execution-interrupted', receipt=asdict(record))

    def prepare_evidence(self,task,record,artifacts):
        from ..contracts.tasks import Resource
        from ..execution.facts import ensure_facts
        reasons=self.hypotheses.get(record.harness_id,())
        if reasons and not any(r.path=='candidate-hypotheses.json' for r in record.artifacts):
            resource=Resource('candidate-hypotheses.json',artifacts.put(canonical_json([asdict(v)for v in reasons]).encode()),'application/json','diagnostic')
            record=replace(record,artifacts=(*record.artifacts,resource))
        record=ensure_facts(record,artifacts)
        return self.evidence_builder(task,record,artifacts) if self.evidence_builder is not None else record

    def observe(self, kind, amount=1):
        if kind not in self.used or type(amount) is not int or amount < 0:
            raise ValueError('invalid usage observation')
        self.used[kind] += amount

    def record(self, event, **fields):
        clock = current_stage.get()
        if clock is not None and clock.owner is self:
            fields.setdefault('role', clock.stage)
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
        self.observe('model')
        self.record('generator-model-request')
        result = await self.operation(self.completer(system, prompt, signal=self.signal))
        self.record('generator-model-response', text=result)
        return result

    async def operation(self, awaitable, *, stage='editor'):
        role = stage_role(stage)
        active = current_stage.get()
        if active is not None and active.owner is self and active.stage == role:
            self.check()
            return await awaitable
        if self.supervisor.poisoned:
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            raise CleanupError('previous stage retirement was not confirmed')
        if self.signal.is_set():
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            raise asyncio.CancelledError
        started = time.monotonic()
        seconds = getattr(self.plan.timeouts, role + '_seconds')
        clock = StageClock(self, role, started, started + seconds)
        token = current_stage.set(clock)
        self.record('operation-started', role=role, timeout_seconds=seconds)
        status = 'completed'
        try:
            return await self.supervisor.run(lambda: awaitable, timeout=seconds, signal=self.signal)
        except TimeoutError:
            status = 'timeout'
            raise
        except asyncio.CancelledError:
            status = 'cancelled'
            raise
        except BaseException:
            status = 'error'
            raise
        finally:
            current_stage.reset(token)
            self.record('operation-finished', role=role, status=status, elapsed_seconds=time.monotonic() - started)



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

