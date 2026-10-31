"""Execute batches through a shared bounded queue and independent leaf invocations."""
import asyncio
from dataclasses import asdict, replace
from uuid import uuid4
from fruitfly_agent.improvement.contracts.evaluation import CandidateEvaluation, TrialResult
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.improvement.contracts.assessment import AssessmentUnavailable
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.improvement.execution.facts import ensure_facts
from fruitfly_agent.improvement.execution.scheduler import TaskScheduler
from ..workflow.operations import run_stage, require_type, validate_assessment_result
from ..contracts.execution import ExecutionRecord
from ..contracts.assessment import Measurement
from ..contracts.failures import IntegrityError, StageFailure

class BatchEvaluator:

    def __init__(self, context, snapshot, bindings, settings, *, aggregate, assessment=None):
        self.context, self.snapshot, self.settings = (context, snapshot, settings)
        self.assessment = assessment
        self.aggregate = aggregate
        self.entries = {e.key: e for e in snapshot.entries}
        self.backends = {e.key: binding for binding in bindings for e in binding.entries}
        self.scheduler = context.services.own(TaskScheduler(settings.execution.concurrency))
        self.cache, self.evaluations, self.batch_cache = ({}, [], {})

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
        if any((self.entries[key].partition == 'confirmation' for key in batch.task_keys)) and batch.phase != 'confirmation':
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
                self.context.services.record('trial-reused', task_key=key, attempt=attempt, run_id=value.record.run_id if value.record else None)
            else:
                value = await self.trial(plan, harness, entry, attempt, assess=batch.phase == 'search')
                self.cache[cache_key] = value
            completed.append(value)
            self.persist('executions', evaluation_id + '-' + key + '-' + str(attempt), asdict(value))
            return value
        failure = None
        try:
            await self.scheduler.map(tuple((lambda key=key, attempt=attempt: execute(key, attempt) for key in batch.task_keys for attempt in range(batch.attempts))))
        except BaseException as exc:
            failure = exc
        ordered = tuple(sorted(completed, key=lambda t: (batch.task_keys.index(t.task_key), t.attempt)))
        result = CandidateEvaluation(evaluation_id, harness.snapshot_id, plan.conditions_id, batch, ordered, self.aggregate(self.snapshot, batch, ordered, self.settings.evaluation))
        self.evaluations.append(result)
        self.persist('evaluations', evaluation_id, asdict(result))
        if failure is not None:
            raise failure
        self.batch_cache[identity] = result
        return result

    async def trial(self, plan, harness, entry, attempt, *, assess=True):
        parent = self.context.services
        services = WorkflowServices(plan, signal=parent.signal,
            record=lambda event, **fields: parent.record(event, task_key=entry.key, attempt=attempt, **fields))
        services.evidence_builder = parent.evidence_builder
        services.hypotheses = parent.hypotheses
        context = replace(self.context, services=services)
        record = measurement = None
        error = ''
        parent.record('trial-started', task_key=entry.key, attempt=attempt, harness_id=harness.snapshot_id)
        try:
            binding = self.backends[entry.key]
            try:
                source_id = binding.current_source()
            except Exception as exc:
                raise IntegrityError('task collection source cannot be validated') from exc
            if source_id != binding.source_id:
                raise IntegrityError('task collection changed during execution')
            ports = binding.build(context)
            runner = services.own(ports.runner)
            services.observe('execution', getattr(runner, 'execution_charge', 1))
            record = await run_stage(services, 'execute', lambda: runner.execute(plan, entry.task, harness),
                validator=lambda value: require_type(value, ExecutionRecord))
            if record.task_id != entry.task.task_id or record.material_id != entry.task.material_id or record.harness_id != harness.snapshot_id or (record.conditions_id != plan.conditions_id) or (record.initial_state_id != plan.parent.state):
                raise IntegrityError('trial receipt differs from frozen task, harness or conditions')
            record = services.prepare_evidence(entry.task,record,context.artifacts)
            if record.status == 'completed' and ports.measurements is not None:
                measurement = await run_stage(services, 'measure', lambda: ports.measurements.measure(entry.task, record),
                    validator=lambda value: require_type(value, Measurement, optional=True))
                if measurement is not None and measurement.run_id != record.run_id:
                    raise IntegrityError('trial measurement belongs to another execution')
            if self.assessment is not None and assess:
                record, values = await run_stage(services, 'assess', lambda: self.assessment.assess(entry.task, record),
                    validator=lambda value: validate_assessment_result(value, record))
        except (AssessmentUnavailable, IntegrityError, asyncio.CancelledError) as exc:
            error = type(exc).__name__
            raise
        except StageFailure as exc:
            parent.check()
            record = exc.record
            if record is not None and (record.task_id != entry.task.task_id or record.material_id != entry.task.material_id or record.harness_id != harness.snapshot_id or (record.conditions_id != plan.conditions_id) or (record.initial_state_id != plan.parent.state)):
                raise IntegrityError('interrupted receipt differs from frozen task or conditions')
            error = exc.failure.code
            if exc.failure.stage == 'execute' and error == 'timeout':
                from .facts import timed_out
                record = record or ExecutionRecord('timeout-' + uuid4().hex, entry.task.task_id,
                    entry.task.material_id, harness.snapshot_id, plan.parent.state,
                    plan.conditions_id, 'error', 'Execution timed out before a complete receipt.')
                record = services.prepare_evidence(entry.task, timed_out(record, context.artifacts), context.artifacts)
        except Exception as exc:
            parent.check()
            error = type(exc).__name__
        finally:
            try:
                parent.record('trial-finished', task_key=entry.key, attempt=attempt, run_id=record.run_id if record else None, error=error or None)
                if record is not None:
                    parent.record('leaf-receipt', task_key=entry.key, attempt=attempt, receipt=asdict(record), measurement=asdict(measurement) if measurement is not None else None)
            finally:
                await services.close()
                for kind, amount in services.used.items():
                    parent.observe(kind, amount)
        return TrialResult(entry.key, attempt, record, measurement, error)
