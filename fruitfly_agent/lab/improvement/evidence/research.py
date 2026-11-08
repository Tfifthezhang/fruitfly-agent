"""Readable retained-batch evidence without fabricated evaluation structures."""
from dataclasses import asdict
from .resources import ReferenceWorkspace
from .access import EvidenceAccess
from fruitfly_agent.improvement.contracts.versions import canonical_json


def build_workspace(request, artifacts, *, record=None):
    references = {}
    def put(path, value):
        references[path] = artifacts.put(canonical_json(value).encode())
    put('context/edit-grants.json', {'component_ids': request.plan.component_ids,
        'options': request.plan.component_options})
    tasks = []
    for task in request.tasks:
        prefix = 'context/tasks/' + task.task_id
        put(prefix + '/metadata.json', {'task_id': task.task_id, 'material_id': task.material_id,
            'origin': task.origin, 'instruction': task.instruction})
        for resource in task.inputs:
            references[prefix + '/inputs/' + resource.path] = resource.artifact_id
        tasks.append({'task_id': task.task_id, 'path': prefix + '/metadata.json'})
    rows = []
    for receipt in request.records:
        prefix = 'context/executions/' + receipt.run_id
        put(prefix + '/metadata.json', asdict(receipt))
        references[prefix + '/output.txt'] = artifacts.put(receipt.output.encode())
        for resource in receipt.artifacts:
            references[prefix + '/' + resource.path] = resource.artifact_id
        rows.append({'run_id': receipt.run_id, 'task_id': receipt.task_id,
            'harness_id': receipt.harness_id, 'status': receipt.status,
            'metadata': prefix + '/metadata.json'})
    put('context/executions.json', rows)
    put('context/tasks.json', tasks)
    for resource in request.context:
        references['context/extensions/' + resource.path] = resource.artifact_id
    put('INDEX.json', {'files': ['context/tasks.json', 'context/executions.json',
        'context/edit-grants.json'], 'task_count': len(tasks), 'execution_count': len(rows),
        'navigation': 'Search and read selected original evidence; observations do not establish causes.'})
    return ReferenceWorkspace(artifacts=artifacts, references=references, baseline=request.baseline,
        files={}, writable_ids=request.plan.component_ids, record=record,
        access=EvidenceAccess((r.run_id for r in request.records), record=record))
