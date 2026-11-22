"""Batch readability uses immutable references outside writable candidate storage."""
import json

from fruitfly_agent.improvement.contracts.components import ComponentDocument, HarnessSnapshot
from fruitfly_agent.improvement.contracts.versions import canonical_json
from ..evidence.resources import ReferenceWorkspace
from ..evidence.access import EvidenceAccess
from ..evidence.investigation import selected_records, receipt_metadata, selected_materials
from ..evidence.batch import batch_view, context_observations


def build_workspace(request, artifacts, *, record=None):
    references, tasks = {}, []
    for resource in request.context:
        references['context/extensions/' + resource.path] = resource.artifact_id
    records = selected_records(request, artifacts)
    task_ids = {r.task_id for r in records}
    selection = next((resource for resource in request.context if resource.path == 'selection.json'), None)
    grouped = selection and json.loads(artifacts.read(selection.artifact_id)).get(
        'implementation_id') == 'focused-group-material-v1'
    for task in request.tasks:
        if not grouped and task.task_id not in task_ids:
            continue
        path = 'context/tasks/' + task.task_id + '/task.md'
        references[path] = artifacts.put(task.instruction.encode())
        rows = []
        for receipt in records:
            if receipt.task_id != task.task_id:
                continue
            prefix = 'context/executions/' + receipt.run_id
            references[prefix + '/metadata.json'] = artifacts.put(canonical_json(receipt_metadata(receipt)).encode())
            output = prefix + '/output.txt'
            references[output] = artifacts.put(receipt.output.encode())
            for resource in selected_materials(request, artifacts, receipt):
                references[prefix + '/' + resource.path] = resource.artifact_id
            sources = prefix + '/sources.json'
            references[sources] = artifacts.put(canonical_json({'resources': [
                {'path': prefix + '/' + r.path, 'kind': r.kind, 'artifact_id': r.artifact_id}
                for r in selected_materials(request, artifacts, receipt)]}).encode())
            overview = prefix + '/evidence/overview.json'
            rows.append({'run_id': receipt.run_id, 'status': receipt.status, 'output': output,
                'sources': sources, 'overview': overview if overview in references else None})
        tasks.append({'task_id': task.task_id, 'task': path, 'executions': rows})
    for name, value in batch_view(request.tasks, request.records,
            context_observations(request.context, artifacts), artifacts).items():
        if name == 'executions.json':
            for summary in value:
                references['context/summaries/' + summary['run_id'] + '.json'] = artifacts.put(canonical_json(summary).encode())
            for row in value:
                row['detailed_grant'] = row['run_id'] in {r.run_id for r in records}
                if not row['detailed_grant']:
                    row['metadata'] = None
                if row.get('overview') not in references:
                    row['overview'] = None
        references['context/' + name] = artifacts.put(canonical_json(value).encode())
    material_scope = {'execution_count': len(request.records),
        'detailed_execution_count': len(records),
        'granted_resource_count': len(references),
        'selection_path': 'context/extensions/selection.json' if selection else None,
        'instructions': 'Browse exact granted paths with catalog(prefix=...). The selection receipt is authorization metadata, not required full reading.'}
    references['context/material-scope.json'] = artifacts.put(canonical_json(material_scope).encode())
    batch = {'material_scope': 'context/material-scope.json', 'statistics': 'context/statistics.json', 'overview': 'context/overview.json', 'executions': 'context/executions.json',
        'coverage': 'context/coverage.json',
        'selection': 'context/extensions/selection.json' if any(r.path == 'selection.json' for r in request.context) else None, 'tasks': tasks, 'instruction': request.instruction,
        'scope': 'Granted records for reading. Execution status and measurements are observations, not judgments.'}
    references['context/batch.json'] = artifacts.put(canonical_json(batch).encode())
    placeholder = HarnessSnapshot((ComponentDocument('organization', 'organization', 'I', 'organization-v1', ()),))
    return ReferenceWorkspace(artifacts=artifacts, references=references, baseline=placeholder,
        files={}, writable_ids=(), record=record,
        access=EvidenceAccess((r.run_id for r in request.records), record=record)), batch
