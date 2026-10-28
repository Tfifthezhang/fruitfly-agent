"""Optional process-guided next seed, distinct from joint objective selection."""
import asyncio
from fruitfly_agent.improvement.contracts.assessment import AssessmentUnavailable
from fruitfly_agent.improvement.workflow.budget import AllocationExhausted
from .completed import completed_input


async def choose_seed(service, snapshot, evaluations, incumbent):
    if service is None:
        return incumbent, 'Completed assessment is disabled.'
    candidates = tuple(e for e in evaluations if e.complete)
    if len(candidates) < 2:
        return incumbent, 'Only one complete batch is available.'
    try:
        comparator = next((a for a in service.assessors if callable(getattr(a, 'compare_batches', None))), None)
        if comparator is None:
            raise AssessmentUnavailable('completed assessor has no batch comparator')
        tasks = {e.key: e.task for e in snapshot.entries}
        inputs = {e.evaluation_id: tuple(completed_input(tasks[t.task_key], t.record, service.artifacts)
            for t in e.trials if t.record is not None) for e in candidates}
        data = await service.services.operation(asyncio.wait_for(
            comparator.compare_batches(inputs, incumbent.evaluation_id), service.settings.timeout_seconds))
        if (not isinstance(data, dict) or set(data) != {'evaluation_id', 'reason', 'evidence_ids'}
                or not isinstance(data['reason'], str) or not 0 < len(data['reason']) <= 4000
                or not isinstance(data['evidence_ids'], list) or not data['evidence_ids']
                or set(data['evidence_ids']) - {ref for group in inputs.values() for value in group for ref in value.evidence_ids}):
            raise ValueError('invalid batch process comparison')
        chosen = next((e for e in candidates if e.evaluation_id == data['evaluation_id']), None)
        if chosen is None:
            raise ValueError('process comparison chose an unavailable evaluation')
        return chosen, data['reason']
    except (AllocationExhausted, asyncio.CancelledError):
        raise
    except Exception as exc:
        service.services.check()
        if service.settings.required:
            raise AssessmentUnavailable(type(exc).__name__) from exc
        return incumbent, 'Process comparison unavailable; retain objective incumbent: ' + type(exc).__name__
