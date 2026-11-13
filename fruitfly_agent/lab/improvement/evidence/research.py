"""Readable retained-batch evidence without fabricated evaluation structures."""
from .resources import ReferenceWorkspace
from .access import EvidenceAccess
from .investigation import selected_records, receipt_metadata, selected_materials
from .batch import batch_view, context_observations
from fruitfly_agent.improvement.contracts.versions import canonical_json


def build_workspace(request, artifacts, *, record=None):
    references = {}
    def put(path, value):
        references[path] = artifacts.put(canonical_json(value).encode())
    put('context/edit-grants.json', {'component_ids': request.plan.component_ids,
        'options': request.plan.component_options})
    records = selected_records(request, artifacts)
    task_ids = {r.task_id for r in records}
    tasks = []
    for task in request.tasks:
        if task.task_id not in task_ids:
            continue
        prefix = 'context/tasks/' + task.task_id
        put(prefix + '/metadata.json', {'task_id': task.task_id, 'material_id': task.material_id,
            'origin': task.origin, 'instruction': task.instruction})
        for resource in task.inputs:
            references[prefix + '/inputs/' + resource.path] = resource.artifact_id
        tasks.append({'task_id': task.task_id, 'path': prefix + '/metadata.json'})
    rows = []
    for receipt in records:
        prefix = 'context/executions/' + receipt.run_id
        put(prefix + '/metadata.json', receipt_metadata(receipt))
        references[prefix + '/output.txt'] = artifacts.put(receipt.output.encode())
        for resource in selected_materials(request, artifacts, receipt):
            references[prefix + '/' + resource.path] = resource.artifact_id
        rows.append({'run_id': receipt.run_id, 'task_id': receipt.task_id,
            'harness_id': receipt.harness_id, 'status': receipt.status,
            'metadata': prefix + '/metadata.json'})
    for name, value in batch_view(request.tasks, request.records,
            context_observations(request.context, artifacts), artifacts).items():
        if name == 'executions.json':
            for row in value:
                row['detailed_grant'] = row['run_id'] in {r.run_id for r in records}
                if not row['detailed_grant']:
                    row['metadata'] = None
                if row.get('overview') not in references:
                    row['overview'] = None
        put('context/' + name, value)
    put('context/tasks.json', tasks)
    for resource in request.context:
        references['context/extensions/' + resource.path] = resource.artifact_id
    put('INDEX.json', {'files': ['context/tasks.json', 'context/executions.json',
        'context/edit-grants.json', 'context/extensions/selection.json', 'context/overview.json', 'context/coverage.json'], 'task_count': len(tasks), 'execution_count': len(rows),
        'navigation': 'Search and read selected original evidence; observations do not establish causes.'})
    return ReferenceWorkspace(artifacts=artifacts, references=references, baseline=request.baseline,
        files={}, writable_ids=request.plan.component_ids, record=record,
        access=EvidenceAccess((r.run_id for r in records), record=record))
