"""Batch readability uses immutable references outside writable candidate storage."""
from dataclasses import asdict
from fruitfly_agent.improvement.contracts.components import ComponentDocument, HarnessSnapshot
from fruitfly_agent.improvement.contracts.versions import canonical_json
from ..evidence.resources import ReferenceWorkspace


def build_workspace(request, artifacts, *, record=None):
    references, tasks = {}, []
    for resource in request.context:
        references['context/extensions/' + resource.path] = resource.artifact_id
    for task in request.tasks:
        path = 'context/tasks/' + task.task_id + '/task.md'
        references[path] = artifacts.put(task.instruction.encode())
        rows = []
        for receipt in request.records:
            if receipt.task_id != task.task_id:
                continue
            prefix = 'context/tasks/' + task.task_id + '/executions/' + receipt.run_id
            output = prefix + '/output.txt'
            references[output] = artifacts.put(receipt.output.encode())
            for resource in receipt.artifacts:
                references[prefix + '/' + resource.path] = resource.artifact_id
            sources = prefix + '/sources.json'
            references[sources] = artifacts.put(canonical_json({'resources': [
                {'path': prefix + '/' + r.path, 'kind': r.kind, 'artifact_id': r.artifact_id}
                for r in receipt.artifacts]}).encode())
            overview = prefix + '/evidence/overview.json'
            rows.append({'run_id': receipt.run_id, 'status': receipt.status, 'output': output,
                'sources': sources, 'overview': overview if overview in references else None})
        tasks.append({'task_id': task.task_id, 'task': path, 'executions': rows})
    batch = {'tasks': tasks, 'instruction': request.instruction,
        'scope': 'Granted records for reading. Execution status and measurements are observations, not judgments.'}
    references['context/batch.json'] = artifacts.put(canonical_json(batch).encode())
    placeholder = HarnessSnapshot((ComponentDocument('organization', 'organization', 'I', 'organization-v1', ()),))
    return ReferenceWorkspace(artifacts=artifacts, references=references, baseline=placeholder,
        files={}, writable_ids=(), record=record), batch
