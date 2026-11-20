"""Model judgments for an explicitly granted set of batches."""
from fruitfly_agent.improvement.contracts.assessment import AssessmentUnavailable
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash


async def compare_model(ports, batches, *, context, input_ids, policy):
    if ports.assessor is None:
        raise ValueError('register an Assessor role before comparison')
    tasks = {task.task_id: task for batch in batches for task in batch.tasks}
    judgments = []
    async with ports.create_services() as services:
        assessor = ports.assessor(services)
        assessor.evaluator.context = context
        for key, task in tasks.items():
            records = tuple(record for batch in batches for record in batch.records if record.task_id == key)
            try:
                data, reference = await assessor.evaluator.evaluate(task, records, services)
                judgments.append({'task_id': key, 'judgment_id': reference, 'judgment': data})
            except AssessmentUnavailable as exc:
                judgments.append({'task_id': key, 'status': 'unavailable', 'detail': str(exc)})
    available = sum('judgment' in entry for entry in judgments)
    return {
        'method': 'model', 'policy_id': content_hash(canonical_json(policy)), 'inputs': input_ids,
        'coverage': {'tasks': len(tasks), 'judged': available},
        'usage': {'comparison_model_calls': None},
        'assurance': 'model-judgment' if available else 'insufficient',
        'conclusion': 'per-task-judgments' if available else 'insufficient',
        'judgments': judgments,
    }
