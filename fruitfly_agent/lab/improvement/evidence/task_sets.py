"""Project only granted development tasks, facts and results for joint editing."""
from dataclasses import asdict
from .resources import ReferenceWorkspace
from .access import EvidenceAccess
from fruitfly_agent.improvement.contracts.versions import canonical_json


def build_workspace(request, artifacts, *, record=None):
    files, references = {'context/edit-grants.json': canonical_json({
        'component_ids': request.plan.component_ids, 'options': request.plan.component_options}).encode()}, {}
    allowed = {entry.key: entry for entry in request.tasks}
    if any(entry.partition != 'development' for entry in request.tasks):
        raise ValueError('private task partitions cannot enter editing')
    for entry in request.tasks:
        prefix = 'context/tasks/' + entry.key
        files[prefix + '/task.md'] = entry.task.instruction.encode()
        files[prefix + '/metadata.json'] = canonical_json({
            'collection_id': entry.collection_id, 'key': entry.key,
            'material_id': entry.task.material_id, 'objective': asdict(entry.objective)}).encode()
        for resource in entry.task.inputs:
            references[prefix + '/inputs/' + resource.path] = resource.artifact_id
    evaluations = []
    for evaluation in request.evaluations:
        if evaluation.batch.phase != 'search' or set(evaluation.batch.task_keys) - set(allowed):
            raise ValueError('editor evaluation is outside the development grant')
        trials = []
        for trial in evaluation.trials:
            if trial.record is None:
                trials.append({'task_key': trial.task_key, 'attempt': trial.attempt, 'error': trial.error})
                continue
            receipt = trial.record
            prefix = 'context/tasks/' + trial.task_key + '/executions/' + receipt.run_id
            files[prefix + '/output.txt'] = receipt.output.encode()
            for resource in receipt.artifacts:
                references[prefix + '/' + resource.path] = resource.artifact_id
            trials.append({'task_key': trial.task_key, 'attempt': trial.attempt, 'run_id': receipt.run_id,
                'status': receipt.status, 'score': trial.measurement.score if trial.measurement else None,
                'policy_id': trial.measurement.policy_id if trial.measurement else None, 'error': trial.error})
        evaluations.append({'evaluation_id': evaluation.evaluation_id, 'harness_id': evaluation.harness_id,
            'batch': asdict(evaluation.batch), 'assessment': asdict(evaluation.assessment), 'trials': trials})
    for resource in getattr(request, 'context', ()):
        references['context/extensions/' + resource.path] = resource.artifact_id
    files['context/evaluations.json'] = canonical_json(evaluations).encode()
    files['context/task-set.json'] = canonical_json({'task_set_id': request.task_set_id,
        'development_tasks': sorted(allowed)}).encode()
    for index, candidate in enumerate(request.history):
        files[f'context/candidates/{index}.json'] = canonical_json(asdict(candidate)).encode()
    files['INDEX.json'] = canonical_json({'files': sorted((*files, *references)),
        'writable_components': request.plan.component_ids}).encode()
    return ReferenceWorkspace(artifacts=artifacts, references=references, baseline=request.baseline,
        files=files, writable_ids=request.plan.component_ids, record=record,
        access=EvidenceAccess((r.run_id for r in request.records), record=record))
