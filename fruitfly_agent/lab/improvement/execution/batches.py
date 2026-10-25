"""Execute batches through a shared bounded queue and per-trial child allocations."""
import asyncio
from dataclasses import asdict, replace
from uuid import uuid4

from ..contracts.evaluation import CandidateEvaluation, TrialResult
from ..contracts.versions import canonical_json
from ..contracts.assessment import AssessmentUnavailable
from ..workflow.budget import AllocationExhausted
from ..workflow.services import WorkflowServices
from .facts import ensure_facts
from .scheduler import TaskScheduler


class BatchEvaluator:
    def __init__(self, context, snapshot, bindings, settings, *, aggregate, assessment=None):
        self.context, self.snapshot, self.settings = context, snapshot, settings
        self.assessment = assessment
        self.aggregate = aggregate
        self.entries = {e.key: e for e in snapshot.entries}
        self.backends = {e.key: binding for binding in bindings for e in binding.entries}
        self.scheduler = context.services.own(TaskScheduler(settings.execution.concurrency))
        self.cache, self.evaluations, self.batch_cache = {}, [], {}
        self.condition = asyncio.Condition()
        self.in_flight = 0

    def persist(self, kind, name, value):
        reference = self.context.artifacts.put(canonical_json(value).encode())
        save = getattr(self.context, 'save_record', None)
        if save is not None:
            save(kind + '/' + name + '.json', value)
        self.context.services.record(kind.rstrip('s') + '-saved', id=name, evidence=reference)
        return reference

    async def evaluate(self, plan, harness, batch, *, fresh=False):
        if batch.task_set_id != self.snapshot.snapshot_id or set(batch.task_keys) - set(self.entries):
            raise ValueError('batch differs from frozen task set')
        if any(self.entries[key].partition == 'confirmation' for key in batch.task_keys) and batch.phase != 'confirmation':
            raise ValueError('confirmation tasks cannot enter development execution')
        identity = (harness.snapshot_id, plan.conditions_id, batch.batch_id)
        if not fresh and identity in self.batch_cache:
            return self.batch_cache[identity]
        evaluation_id = 'evaluation-' + uuid4().hex
        self.persist('batches', batch.batch_id[7:], asdict(batch))
        completed = []

        async def execute(key, attempt):
            entry = self.entries[key]
            cache_key = (harness.snapshot_id, key, plan.conditions_id, attempt)
            if not fresh and cache_key in self.cache:
                value = self.cache[cache_key]
                self.context.services.record('trial-reused', task_key=key, attempt=attempt,
                    run_id=value.record.run_id if value.record else None)
            else:
                value = await self.trial(plan, harness, entry, attempt, assess=batch.phase == 'search')
                self.cache[cache_key] = value
            completed.append(value)
            self.persist('executions', evaluation_id + '-' + key + '-' + str(attempt), asdict(value))
            return value

        failure = None
        try:
            await self.scheduler.map(tuple(lambda key=key, attempt=attempt: execute(key, attempt)
                for key in batch.task_keys for attempt in range(batch.attempts)))
        except BaseException as exc:
            failure = exc
        ordered = tuple(sorted(completed, key=lambda t: (batch.task_keys.index(t.task_key), t.attempt)))
        result = CandidateEvaluation(evaluation_id, harness.snapshot_id, plan.conditions_id, batch,
            ordered, self.aggregate(self.snapshot, batch, ordered, self.settings.evaluation))
        self.evaluations.append(result)
        self.persist('evaluations', evaluation_id, asdict(result))
        if failure is not None:
            raise failure
        self.batch_cache[identity] = result
        return result

    async def trial(self, plan, harness, entry, attempt, *, assess=True):
        parent = self.context.services
        # Wait only for live sibling reservations, never for a protected final phase.
        async with self.condition:
            while entry.model_limit > parent.budget.available('model') or parent.budget.available('execution') < entry.execution_limit:
                if not self.in_flight:
                    raise AllocationExhausted('remaining allowance cannot fund the next task')
                await self.condition.wait()
                parent.check()
            scope = parent.budget.child({'model': entry.model_limit, 'execution': entry.execution_limit})
            self.in_flight += 1
        services = WorkflowServices(plan, budget=scope,
            record=lambda event, **fields: parent.record(event, task_key=entry.key, attempt=attempt, **fields))
        context = replace(self.context, services=services)
        record = measurement = None
        error = ''
        parent.record('trial-started', task_key=entry.key, attempt=attempt, harness_id=harness.snapshot_id,
            model_limit=entry.model_limit)
        try:
            binding = self.backends[entry.key]
            if binding.current_source() != binding.source_id:
                raise ValueError('task collection changed during execution')
            ports = binding.build(context)
            runner = services.own(ports.runner)
            services.reserve('execution', getattr(runner, 'execution_charge', 1))
            record = await services.operation(runner.execute(plan, entry.task, harness))
            if (record.task_id != entry.task.task_id or record.material_id != entry.task.material_id
                    or record.harness_id != harness.snapshot_id or record.conditions_id != plan.conditions_id
                    or record.initial_state_id != plan.parent.state):
                raise ValueError('trial receipt differs from frozen task, harness or conditions')
            record = ensure_facts(record, context.artifacts)
            if record.status == 'completed' and ports.measurements is not None:
                measurement = await services.operation(ports.measurements.measure(entry.task, record))
            if self.assessment is not None and assess:
                record, values = await self.assessment.assess(entry.task, record)
                self.assessment.ensure_available()
        except (AllocationExhausted, AssessmentUnavailable, asyncio.CancelledError) as exc:
            error = type(exc).__name__
            raise
        except Exception as exc:
            parent.check()
            error = type(exc).__name__
        finally:
            parent.record('trial-finished', task_key=entry.key, attempt=attempt,
                run_id=record.run_id if record else None, error=error or None)
            if record is not None:
                parent.record('leaf-receipt', task_key=entry.key, attempt=attempt,
                    receipt=asdict(record), measurement=asdict(measurement) if measurement is not None else None)
            await services.close()
            async with self.condition:
                self.in_flight -= 1
                self.condition.notify_all()
        return TrialResult(entry.key, attempt, record, measurement, error)
