"""A public TaskRunner backed by fixed-version Eval jobs and observed usage."""
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
import json
import asyncio
from fruitfly_agent.improvement.contracts.failures import IntegrityError

from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.execution.handles import ManagedExecution
from .building import RuntimeConfigBuilder
from .evidence import collect
from .process import EvalProcess
from .facts import attach_benchmark_facts


class EvalTaskRunner:
    capabilities = frozenset({'benchmark-task', 'events', 'stop', 'execution-config', 'configuration-materialization'})

    def __init__(self, context, prepared, measurements, *, executor=None):
        self.context, self.prepared, self.measurements = context, prepared, measurements
        self.capabilities = type(self).capabilities | frozenset("tool:" + tool.name for tool in context.config.tools) if context.config is not None else type(self).capabilities
        self.executor = executor or EvalProcess()
        self.builder = RuntimeConfigBuilder(context.workspace, prepared.request.runtime, context.components)

    async def start(self, plan, task, harness):
        run_id = 'benchmark-' + uuid4().hex
        async def execute(journal):
            return await self.execute_trial(plan, task, harness, run_id, journal)
        return ManagedExecution(execute, execution_id=run_id, version_id=harness.snapshot_id,
            artifacts=self.context.artifacts, record=self.context.services.record)

    async def execute(self, plan, task, harness):
        handle = await self.start(plan, task, harness)
        try:
            return await handle.result()
        finally:
            await handle.aclose()

    def observe_requests(self, record):
        for resource in record.artifacts:
            if resource.path.endswith('/model-usage.json'):
                try:
                    rows = json.loads(self.context.artifacts.read(resource.artifact_id))['requests']
                    for row in rows:
                        self.context.services.record('request', id=row['id'], model=row.get('model'))
                        self.context.services.record('response', attempt_id=row['id'],
                            status=row['status'], usage=row['usage'], elapsed_seconds=row.get('elapsed_seconds'))
                except (KeyError, TypeError, ValueError):
                    self.context.services.record('external-usage-unavailable', run_id=record.run_id)

    async def execute_trial(self, plan, task, harness, run_id, journal):
        context, frozen = self.context, self.prepared
        try:
            source_id = frozen.current_source()
        except Exception as exc:
            raise IntegrityError('benchmark source cannot be validated') from exc
        if source_id != frozen.source_id or task != frozen.task:
            raise IntegrityError('benchmark material or execution conditions changed')
        directory = Path(context.workspace) / '.fruitfly/improvement/jobs' / plan.job_id / 'executions' / run_id
        directory.mkdir(parents=True, exist_ok=False)
        config = self.builder.build(harness, destination=directory / 'config.yaml')
        request = replace(frozen.request, runtime=replace(frozen.request.runtime,
            config_path=str(config), profile=self.builder.profile))
        calls = None
        try:
            report, root = await self.executor(request, frozen.host_path, directory=directory,
                output_root=Path(context.workspace) / '.fruitfly/eval', emit=journal.publish)
            artifacts, calls = collect(root, context.artifacts)
            completed = report.get('status') == 'completed' and not report.get('errors')
            reward = next((m.get('value') for m in report.get('metrics', []) if m.get('name') == 'official_reward'), None)
            record = ExecutionRecord(run_id, task.task_id, task.material_id, harness.snapshot_id,
                plan.parent.state, plan.conditions_id, 'completed' if completed else 'error',
                'Benchmark execution completed; inspect Agent trajectory and collected deliverables.' if completed
                else 'Benchmark execution failed; inspect the evaluation record.', artifacts, calls)
            if completed and reward is not None:
                self.measurements.values[run_id] = reward
            record = attach_benchmark_facts(record, root, context.artifacts)
            self.observe_requests(record)
            context.services.record('benchmark-execution', run_id=run_id, evaluation_id=report['evaluation_id'],
                report=str(Path(root) / 'report.json'), model_calls=calls)
            return record
        except asyncio.CancelledError:
            root = getattr(self.executor, 'result_root', None)
            if root is not None:
                try:
                    artifacts, calls = collect(root, context.artifacts, interrupted=True)
                    record = ExecutionRecord(run_id, task.task_id, task.material_id, harness.snapshot_id,
                        plan.parent.state, plan.conditions_id, 'cancelled',
                        'Benchmark execution interrupted; partial evidence is not an official score.', artifacts, calls)
                    record = attach_benchmark_facts(record, root, context.artifacts, interrupted=True)
                    self.observe_requests(record)
                    context.services.retain_execution(record)
                except (OSError, ValueError, KeyError) as exc:
                    context.services.record('interrupted-collection-failed', error=type(exc).__name__)
            raise
        finally:
            if calls is not None:
                context.services.observe('model', calls)
            context.services.record('external-usage', run_id=run_id, observed_calls=calls)
