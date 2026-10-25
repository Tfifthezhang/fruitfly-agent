"""Durable RSI with a shared root and existing verification/adoption semantics."""
import time

from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.improvement.api import BudgetScope
from fruitfly_agent.lab.rsi import PersistentEvolutionDriver
from fruitfly_agent.run.evolution import RunEvolutionHost
from ..composition import application_factory
from ..policies import stop_policy
from . import observe


async def run(prepared, record, records, emit, *, resume=False, factory=None):
    directory = records.directory(record['id'])
    if resume:
        runtime_path = directory / 'runtime/config.yaml'
        if prepared.summary() != record['configuration']:
            raise ValueError('experiment conditions changed; cannot resume this run')
    else:
        prepared.verify_sources()
        runtime_path = prepared.stage_runtime(directory)
    factory = factory or application_factory(prepared, runtime_path)
    application = AgentApplication(factory)
    options = prepared.config.rsi
    budget = BudgetScope({'model': options.max_model_calls, 'execution': options.max_executions},
        deadline=time.monotonic() + options.timeout_seconds)
    try:
        await application.start()
        # Validate material, capabilities and verification before the driver starts paid phases.
        if not resume:
            application.workflow_preview(prepared.request)
        host = RunEvolutionHost(application, factory, policy_id=prepared.policy_id, request=prepared.request, budget=budget)
        record['links']['rsi'] = record['id']
        records.save(record)
        job = await observe(application, PersistentEvolutionDriver().evolve(host, job_id=record['id'], policy_id=prepared.policy_id,
            direction=prepared.request.direction or 'Improve the declared components using task execution evidence.',
            max_steps=options.max_generations, phase_timeout_seconds=options.phase_timeout,
            continue_on_rejection=options.continue_on_rejection, stop_policy=stop_policy(prepared.config.stop.get('rsi'))),
            record, records, emit)
        record['usage'] = dict(budget.used)
        record['usage_kind'] = 'charged allowance; actual unknown work is identified in child job reports'
        record['stop_reason'] = job.stop_reason
        record['evolution_phase'] = job.phase
        if job.phase in {'interrupted', 'failed', 'stale'}:
            record['status'] = job.phase
        return {'id': record['id'], 'status': job.phase, 'stop_reason': job.stop_reason, 'usage': dict(budget.used)}
    finally:
        record['usage'] = dict(budget.used)
        record['links']['improvement_runs'] = [r.run_id for r in application.improvement_history()] if application.state.value == 'idle' else []
        await application.close()
        budget.close()
