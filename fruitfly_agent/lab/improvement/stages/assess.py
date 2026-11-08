"""One independent research stage over injected capabilities."""
from fruitfly_agent.improvement.contracts.activities import ActivityResult
from .context import readable_context
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.research import ResearchBatch

async def assess(ports, spec, inputs):
    if ports.assessor is None:
        raise ValueError('register an Assessor role before assessment')
    batch = ports.input_batch(inputs.batches)
    tasks = {t.task_id: t for t in batch.tasks}
    async with ports.create_services() as services:
        assessor = ports.assessor(services)
        assessor.evaluator.context = readable_context(ports, inputs)
        records = []
        for record in batch.records:
            from fruitfly_agent.improvement.contracts.assessment import AssessmentUnavailable
            try:
                updated, _ = await assessor.assess(tasks[record.task_id], record)
            except AssessmentUnavailable as exc:
                from dataclasses import replace
                reference = ports.put('assessment.json', {'status': 'unavailable', 'detail': str(exc),
                    'run_id': record.run_id})
                updated = replace(record, artifacts=(*record.artifacts, reference))
            records.append(updated)
        result = ResearchBatch(batch.tasks, tuple(records), batch.observations)
        return ActivityResult((ports.put('batch.json', result.to_dict()),))
