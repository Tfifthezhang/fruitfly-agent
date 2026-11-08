"""One independent research stage over injected capabilities."""
from fruitfly_agent.improvement.contracts.activities import ActivityResult
from .context import readable_context
from fruitfly_agent.improvement.contracts.tasks import Resource

async def compare(ports, spec, inputs):
    if ports.assessor is None:
        raise ValueError('register an Assessor role before comparison')
    batches = [ports.read_batch(resource) for resource in inputs.batches]
    tasks = {t.task_id: t for b in batches for t in b.tasks}
    async with ports.create_services() as services:
        assessor = ports.assessor(services)
        judgments = []
        assessor.evaluator.context = readable_context(ports, inputs)
        for key, task in tasks.items():
            records = tuple(r for b in batches for r in b.records if r.task_id == key)
            try:
                data, reference = await assessor.evaluator.evaluate(task, records, services)
                judgments.append({'task_id': key, 'judgment_id': reference, 'judgment': data})
            except Exception as exc:
                from fruitfly_agent.improvement.contracts.assessment import AssessmentUnavailable
                if not isinstance(exc, AssessmentUnavailable):
                    raise
                judgments.append({'task_id': key, 'status': 'unavailable', 'detail': str(exc)})
        return ActivityResult((ports.put('comparison.json', {'judgments': judgments}),))
